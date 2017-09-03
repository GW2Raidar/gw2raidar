import requests

GW2_API_BASE = "https://api.guildwars2.com/v2"

class GW2APIException(Exception):
    pass

class GW2API:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def query(self, query):
        headers = None
        if self.api_key:
          headers = {"Authorization": "Bearer %s" % self.api_key}
        r = requests.get(GW2_API_BASE + query, headers=headers)
        if r.status_code != 200:
            try:
                error = r.json()['text']
            except: # TODO make precise?
                error = 'Cannot contact GW2 API'
            raise GW2APIException(error)
        return r.json()

