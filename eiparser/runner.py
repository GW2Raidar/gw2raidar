"""Runs the Elite Insights command line parser on an ArcDPS log and returns its JSON output.

The CLI always exits with 0 once it has started parsing; the outcome of each
file is reported on stdout as a line ``Processed - {json}``.
"""
import gzip
import json
import os
import shutil
import subprocess
import tempfile

RESULT_PREFIX = "Processed - "
DEFAULT_TIMEOUT = 300

# The JSON output feeds the site. The HTML report (with the combat replay) is only made when the caller
# wants to keep it; everything else EI can do is switched off.
CONFIG = """\
SaveAtOut=false
OutLocation={out_dir}
SaveOutHTML={html}
HtmlExternalScripts=false
HtmlCompressJson=false
LightTheme=false
SaveOutCSV=false
SaveOutJSON=true
IndentJSON=false
CompressRaw=false
RawTimelineArrays=false
SaveOutTrace=false
ParsePhases=true
ParseCombatReplay={html}
ComputeDamage=true
ComputeBuff=true
ComputeCast=true
ComputeMechanics=true
ComputeDamageModifiers=false
ParseExtensions=false
SkipFailedTries=false
Anonymous=false
DetailledWvW=false
SingleThreaded={single_threaded}
ParseMultipleLogs=false
UploadToDPSReports=false
UploadToWingman=false
SendEmbedToWebhook=false
SendSimpleMessageToWebhook=false
AutoDiscordBatch=false
"""


class EIParseException(Exception):
    """EI rejected the log (bad or unsupported content); the message is shown to the uploader."""


class EIRunException(Exception):
    """EI could not be run, crashed or timed out."""


def _command(cli):
    return ["dotnet", cli] if cli.lower().endswith(".dll") else [cli]


def _read_result(stdout):
    for line in stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            try:
                return json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                break
    return None


def _load(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as file:
        return json.load(file)


def _generated(result, extensions):
    return [path for path in result.get("generatedFiles") or [] if path.endswith(extensions)]


def parse(evtc_path, cli, timeout=DEFAULT_TIMEOUT, single_threaded=True, report_path=None):
    """Parses ``evtc_path`` (.evtc, .evtc.zip or .zevtc) and returns EI's JSON log as a dict.

    ``cli`` is the path of the GuildWars2EliteInsights-CLI executable, or of its .dll (run through ``dotnet``).
    With ``report_path``, EI also makes its HTML report, including the combat replay; it is written there
    gzip-compressed.
    """
    if not cli:
        raise EIRunException("Elite Insights CLI is not configured (GW2EI_CLI)")

    work_dir = tempfile.mkdtemp(prefix="gw2ei-")
    try:
        config_path = os.path.join(work_dir, "raidar.conf")
        out_dir = os.path.join(work_dir, "out")
        os.mkdir(out_dir)
        with open(config_path, "w") as config:
            config.write(CONFIG.format(out_dir=out_dir, single_threaded="true" if single_threaded else "false",
                                       html="true" if report_path else "false"))

        # EI keeps per-user settings under the home directory; give every run a clean, writable one.
        # On Linux, .NET only reports the per-user settings folders if they already exist, and EI
        # crashes on startup (ArgumentNullException in Settings.Upgrade) when they are missing.
        config_home = os.path.join(work_dir, ".config")
        data_home = os.path.join(work_dir, ".local", "share")
        os.makedirs(config_home)
        os.makedirs(data_home)
        env = dict(os.environ, HOME=work_dir, XDG_CONFIG_HOME=config_home, XDG_DATA_HOME=data_home)
        try:
            process = subprocess.run(_command(cli) + ["-c", config_path, os.path.abspath(evtc_path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work_dir, env=env,
                                     timeout=timeout, universal_newlines=True, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise EIRunException("Elite Insights timed out after %ds" % timeout)
        except OSError as error:
            raise EIRunException("Elite Insights could not be started: %s" % error)

        result = _read_result(process.stdout)
        if result is None:
            raise EIRunException("Elite Insights exited with code %d without a result\n%s\n%s" % (
                process.returncode, process.stdout[-2000:], process.stderr[-2000:]))

        if not result.get("parsed"):
            message = result.get("status") or "Elite Insights could not parse this log"
            if result.get("reason") in ("FileContent", "Setting"):
                raise EIParseException(message)
            raise EIRunException("Elite Insights failed (%s): %s\n%s" % (
                result.get("reason"), message, process.stdout[-2000:]))

        json_files = _generated(result, (".json", ".json.gz"))
        if not json_files:
            raise EIRunException("Elite Insights produced no JSON file: %s" % result.get("status"))
        log = _load(json_files[0])

        if report_path:
            html_files = _generated(result, (".html",))
            if not html_files:
                raise EIRunException("Elite Insights produced no HTML file: %s" % result.get("status"))
            with open(html_files[0], "rb") as source, gzip.open(report_path, "wb", compresslevel=6) as target:
                shutil.copyfileobj(source, target)
        return log
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
