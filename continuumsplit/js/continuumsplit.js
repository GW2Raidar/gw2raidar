'use strict'

/*

TODO:

Display:
 - Class icons
  - Improve selection display
 
Metrics
 - Focus selection
 - Cleave Dps
 - Buffs
 - Boss health
 - Incoming Damage
 - Phase
 - Single target detail pane
 - Skill log

Graphs
 - DPS 


Maps:
 - High res maps (That_Shaman ?)
 - Map out coords
 [ ] VG
 [ ] Gorse
 [ ] Sab
 [ ] Sloth
 [ ] Matthias
 [ ] KC
 [ ] Xera
 [ ] Cairn
 [ ] Mo
 [ ] Samarog
 [ ] Deimos
 [ ] SH
 [ ] Dhuum
 
Map specific mechanics:

VG:
 - RGB circle
 - Glowing sectors
Gorse:
 - Charging circle
 - Orbs
 - Eggs
Sab:
 - Flame wall
 - Cannon state
 - Bomb
 - Platform health?
Sloth:
 - Mushrooms/poison?
 - Slubling form
 - Fire breath
 - Rock stun
 - Fixate
 - Poison
 - CC phases
Matthias:
 - Poison
 - Afflicted
 - Fountain state
 - Icey patch
 - Tornado
 - Chosen
 - Shield
 - Sacrifice
 - Bombs
 - Hadoken?
KC
 - Statues
 - Statue explosion
 - Fixates
 - Bomb
 - Pizza slices?
 - Outer ring (CM)
Xera
 - Shards
 - Empowered
 - Nuggets
 - Orb eating
 - Wall
Cairn
 - Big arm thing
 - Pushes
 - Black waves
 - Circles? Probably not
 - Stunned
 - Agony
 - Teleport countdown (CM)
Mo
 - Protect/Dispel/Claim
 - Floor state
 - Soldiers/etc
 - Spikes
Samarog
 - Shockwave
 - Thunk
 - Spears
 - Stun
 - Rigom/Galosh
 - Friends
Deimos
 - Up/Down
 - Hands?
 - Slices
 - Oil
 - Tears
 - Bubble
 - Saul health
SH
 - Dead
 - Scythes
 - Shrinking platform
 - Walls
 - Fixate
Dhuum
 - Circle
 - Enforcer
 - Deadling
 - Green circles
 - Suck
 - Upper area/pacman
 - Fissures ? I wish
 - Echo (CM)
 - Bubble (end phase?)
 - pizza
 - bomb
 - shackles
*/

class AreaBox {
	constructor(left, right, top, bottom) {
		this.left = left;
		this.top = top;
		this.right = right;
		this.bottom = bottom;
		this.width = right - left;
		this.height = bottom - top;
	}
}

class Point {
	constructor(x, y) {
		this.x = x;
		this.y = y;
		this[0] = x
		this[1] = y
	}		
}

class Sprite {

	constructor(image, srcArea) {
		this.image = image;
		this.srcArea = srcArea;
	}
	
	render(context, x, y, size) {
		context.drawImage(this.image, this.srcArea.left, this.srcArea.top, this.srcArea.width, this.srcArea.height, x - 0.5 * size, y - 0.5 * size, size, size);
	}
}

class Replay {
	    
	constructor(domId, width, height) {
		let replay = this;
		
		// The size to render dots
		this.dotSize = 2
		// The size to render boids
		this.boidSize = 2.5
		// The size to render icons
		this.iconSize = 6
		// Window size (remember for leaving full screen)
		this.windowW = width;
		this.windowH = height;
		// Is the replay currently playing
		this.playing = false
		// Is the replay in fullscreen
		this.fullscreen = false;
		// Current replay time
		this.frameTime = 0
		// Available speeds
		this.speeds = [1, 2, 4, 8]
		// Which speed is selected
		this.speedIndex = 0
		// The portion of width used by the canvas - the rest is for details
		this.canvasPortion = 0.5
		
	    // Image providing all the icons
		this.iconsImage = new Image();
		this.iconsImage.onload = function() {
			replay.downSprite = new Sprite(replay.iconsImage, new AreaBox(32, 63, 0, 32))
			replay.deadSprite = new Sprite(replay.iconsImage, new AreaBox(0, 31, 0, 32))
		}
		this.iconsImage.src = "img/icons.png"
				
        $.get("mapinfo.json", function(data) {
			replay.mapInfo = data;
			if (replay.replayData != null) {
				loadReplayData(replay.replayData)
			}
		});
				
		// Generate html
		this.rootElement = $(domId)
		this.rootElement.append("<div class='replay-container'>" 
		+ "<div class='replay-main'><div class='replay-display'><canvas class='replay-canvas'></canvas></div>"
		+ "<div class='replay-details'>"
		+ "<div class='replay-detail-bossinfo'></div>"
		+ "<div class='replay-detail-player-section'>"
		+ "<div class='replay-detail-table'><div class='replay-detail-header-row'><div class='replay-detail-item'>Player</div><div class='replay-detail-item'>Boss DPS</div><div class='replay-detail-item'>Cleave DPS</div></div>"
		+ "<div class='replay-detail-player-rows'></div></div></div></div></div>"
		+ "<div class='replay-controls'>"
		+ "<button type='button' class='replay-play'><img src='img/play.png'/></button>"
		+ "<input type='range' class='replay-seekbar' value=0></input>"
		+ "<button type='button' class='replay-speed'>1x</button>"
		+ "<button type='button' class='replay-fullscreen'><img src='img/fullscreen.png'/></button>"
		+ "<div class='replay-times'><div class='replay-current-time'>0:00</div> / <div class='replay-total-time'>0:00</div></div></div>"
		+ "</div>");
		this.rootElement.css("width", width + "px")
				
		// Setup canvas
		this.canvas = this.rootElement.find('.replay-canvas')[0]
		this.canvas.width = width * this.canvasPortion
		this.canvas.height = height
		this.canvas.addEventListener("click", function (event) {
			replay.clicked(event.offsetX, event.offsetY)
		});
		this.context = this.canvas.getContext("2d");
		
		// Setup controls
		this.playButton = this.rootElement.find('.replay-play')
		this.playButton.click( function() {
			replay.togglePlay();
		})
		this.speedButton = this.rootElement.find('.replay-speed')
		this.speedButton.click( function() {
			replay.toggleSpeed();
		})
		this.seekbar = this.rootElement.find('.replay-seekbar')
		this.seekbar.change(function() {
		    replay.setFrame(this.valueAsNumber);	
		});
		this.seekbar[0].addEventListener("input", function () { 
			replay.currentTime.text(Replay.printTime(this.valueAsNumber))
		});
		this.seekbar.mousedown(function () {
			replay.pauseToSeek = replay.playing;
			replay.pause();
		});
		this.seekbar.mouseup(function() {
			if (replay.pauseToSeek) {
				replay.play();
			}
		});
		
		this.fullscreenButton = this.rootElement.find('.replay-fullscreen')
		this.fullscreenButton.click(function() {
			replay.toggleFullscreen()
		})
		let fullscreenEndHandler = function () {
			if (replay.fullscreen && !document.fullscreenElement && !document.webkitIsFullScreen && !document.mozFullScreen && !document.msFullscreenElement) {
				replay.toggleFullscreen()
			}
		}
		document.addEventListener('fullscreenchange', fullscreenEndHandler)
		document.addEventListener('webkitfullscreenchange', fullscreenEndHandler)
		document.addEventListener('mozfullscreenchange', fullscreenEndHandler)
		document.addEventListener('MSfullscreenchange', fullscreenEndHandler)
		
		this.currentTime = this.rootElement.find('.replay-current-time')
		this.totalTime = this.rootElement.find('.replay-total-time')
		
		this.playerDetails = this.rootElement.find('.replay-detail-player-rows')
	}
	
	updateDetails() {
		let frameTime = this.frameTime
		$.each(this.frame, function(name, data) {
			if (data.bossdpsDisplay != null) {
				if (frameTime > 0) {
					data.bossdpsDisplay.setValue(Math.trunc(parseInt(data["bossdamage"]) / frameTime))
				} else {
					data.bossdpsDisplay.setValue(0)
				}
				
			}
			if (data.cleavedpsDisplay != null) {
				if (frameTime > 0) {
					data.cleavedpsDisplay.setValue(Math.trunc(parseInt(data["cleavedamage"]) / frameTime))
				} else {
					data.cleavedpsDisplay.setValue(0)
				}
				
			}
		})
		
		this.playerDetails.children().sort(function(a, b) {
			return parseInt($($(b).children()[1]).text()) - parseInt($($(a).children()[1]).text());
		}).appendTo(this.playerDetails)
	}
	
	// Load Replay
	
	loadReplay(replayUrl) {
		let replay = this;
		replay.replayData = null;
		$.get(replayUrl, function(data) {
			replay.replayData = data;
			if (replay.mapInfo != null) {
				replay.loadReplayData(data);
			}
		});
	}
	
	loadReplayData(replayData) {
		this.replayData = replayData;
		this.setupTracks(replayData.tracks);
		this.addPlayerDetailRows(replayData['base-state'])
		let replay = this;
		let maps = this.mapInfo[replayData.info.encounter];
		
		this.mapImage = new Image();
		this.mapImage.onload = function() {
			replay.ready = true
			replay.setFrame(0)
		}
		this.mapImage.src = maps[0].image;
		
		//this.coords = new AreaBox(-12151, -9526, 1976, -274)
		this.coords = new AreaBox(maps[0].worldCoords.left, maps[0].worldCoords.right, maps[0].worldCoords.top, maps[0].worldCoords.bottom)
		this.imageSrc = new AreaBox(maps[0].imageCoords.left, maps[0].imageCoords.right, maps[0].imageCoords.top, maps[0].imageCoords.bottom)		
		this.imageDst = this.calcDstBox()
		this.duration = this.replayData.info.duration
		this.seekbar.attr("max", this.duration)
		this.totalTime.text(Replay.printTime(Math.trunc(this.duration)))
		this.currentTime.text(Replay.printTime(0))
	}
	
	addPlayerDetailRows(actorData) {
		let replay = this;
		this.playerDetails.html("")
		$.each(actorData, function(name, data) {
			if (data["type"] == "Player") {
				let row = $(document.createElement('div'))
				row.addClass('replay-detail-row')
				let nameDisplay = $(document.createElement('div'))
				nameDisplay.addClass('replay-detail-item')
				nameDisplay.text(data["name"])
				row.append(nameDisplay)
				data.bossdpsDisplay = replay.createDisplayBar(50000)
				data.bossdpsDisplay.addClass('replay-detail-item')
				row.append(data.bossdpsDisplay)
				data.cleavedpsDisplay = replay.createDisplayBar(50000)
				data.cleavedpsDisplay.addClass('replay-detail-item')
				row.append(data.cleavedpsDisplay)
				replay.playerDetails.append(row)
			}
		})
	}
	
	createDisplayBar(maxValue) {
		let barRoot = $(document.createElement('div'))
		barRoot.addClass('replay-bar-background')
		let barFill = $(document.createElement('div'))
		barFill.addClass('replay-bar')
		barRoot.append(barFill)
		barRoot.setValue = function(value) {
			barFill.value = value
			barFill.text(value)
			barFill.css('width', Math.trunc(100 * value / maxValue) + '%')
		}
		
		return barRoot;
	}
	
	// Private: Configures tracks after load
	setupTracks(tracks) {
		let replay = this
		$.each(tracks, function(index, track) {
			track['end-time'] = track['start-time'] + (track.data.length - 1) * track.frequency
			switch (track['interpolation']) {
				case 'lerp':
				    track.sampleFunc = Replay.lerp
					break;
				case 'slerp':
					track.sampleFunc = Replay.slerp
					break;
				default:
					track.sampleFunc = Replay.floor
			}
			
			switch (track['update-type']) {
				case 'delta':
					track.lastTime = 0
					track.lastFrame = 0
					track.calcFrame = Replay.deltaTrackCalculator
					break;
				default:
					track.calcFrame = Replay.interpolatingTrackCalculator
			}
		})
	}
		
	// Controls	
		
	toggleFullscreen() {
		if (this.fullscreen) {
			this.fullscreen = false
			if (document.exitFullscreen) {
				document.exitFullscreen();
			} else if (document.webkitExitFullscreen) {
				document.webkitExitFullscreen();
			} else if (document.mozCancelFullScreen) {
				document.mozCancelFullScreen();
			} else if (document.msExitFullscreen) {
				document.msExitFullscreen();
			} else {
				console.log("Fullscreen exit not supported")
			}
			
			this.canvas.width = this.windowW * this.canvasPortion
			this.canvas.height = this.windowH
			this.rootElement.css("width", this.windowW)
			this.imageDst = this.calcDstBox()
			this.renderFrame(this.frameTime)
		} else {

			let replayRoot = this.rootElement[0]
			if (replayRoot.requestFullscreen) {
				replayRoot.requestFullscreen();
			} else if (replayRoot.webkitRequestFullscreen) {
				replayRoot.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT);
			} else if (replayRoot.mozRequestFullScreen) {
				replayRoot.mozRequestFullScreen();
			} else if (replayRoot.msRequestFullscreen) {
				replayRoot.msRequestFullscreen();
			} else {
				console.log("Fullscreen not supported")
				return
			}
			this.fullscreen = true
			this.canvas.width = window.innerWidth * this.canvasPortion
			this.canvas.height = window.innerHeight;
			this.rootElement.css("width", window.innerWidth)
			this.imageDst = this.calcDstBox()
			
			this.renderFrame(this.frameTime)
		}
	}
	
	toggleSpeed() {
		this.speedIndex = (this.speedIndex + 1) % this.speeds.length
		this.speedButton.text(this.speeds[this.speedIndex] + 'x')
	}

	togglePlay() {
		if (this.playing) {
			this.pause();
		} else {
			this.play();
		}
	}
	
	pause() {
		if (this.playing) {
			this.playing = false
			this.playButton.children("img").attr("src", "img/play.png")
		}
	}
	
	play() {
		if (!this.playing && this.ready && this.frameTime < this.duration) {
			let replay = this
			this.lastTime = null;
			this.playing = true;
			this.playButton.children("img").attr("src", "img/pause.png")
			window.requestAnimationFrame(function (time) {replay.playFrame(time)})
		}
	}
	
	playFrame(time) {
		if (this.lastTime == null) {
			this.lastTime = time;
		}
		if (this.playing) {
			let newTime = this.frameTime + (time - this.lastTime) * 0.001 * this.speeds[this.speedIndex]
			this.setFrame(newTime)
		}
		this.lastTime = time;
		if (this.frameTime > this.duration) {
			this.pause();
		}
		if (this.playing) {
			let replay = this
			window.requestAnimationFrame(function (time) {replay.playFrame(time)})
		} 
	}
	
	setFrame(time) {
		this.generateFrame(time)
		this.renderFrame()
		this.updateDetails()
		this.currentTime.text(Replay.printTime(this.frameTime))
		this.seekbar.val(Math.trunc(time))
	}
	
	generateFrame(time) {
		let frameData = $.extend(true, {}, this.replayData["base-state"]);
		$.each(this.replayData.tracks, function(index, track) {
			track.calcFrame(time, frameData)
		})
		this.frame = frameData
		this.frameTime = time
	}
	
	renderFrame() {
		let scale = this.getScale();
		this.context.clearRect(0,0,this.canvas.width, this.canvas.height);
		this.context.fillStyle="#000000";
		this.context.fillRect(0,0,this.canvas.width, this.canvas.height);
		this.context.drawImage(this.mapImage, this.imageSrc.left, this.imageSrc.top, this.imageSrc.width, this.imageSrc.height, this.imageDst.left, this.imageDst.top, this.imageDst.width, this.imageDst.height);		
		let replay = this;
		$.each(this.frame, function(name, data) {
			if (data.position == null) {
				return;
			}
			let pos = replay.convertCoords(data.position.x, data.position.y)
			switch (data.state) {
				case 'Down':
					replay.downSprite.render(replay.context, pos.x, pos.y, replay.iconSize * scale);
					break;
				case 'Dead':
					replay.deadSprite.render(replay.context, pos.x, pos.y, replay.iconSize * scale);
					break;
				default:
					let color = data.color
					replay.context.fillStyle=color;
					replay.context.beginPath()			
					if (data.heading != null) {						
						let headingX = Math.sin(data.heading)
						let headingY = Math.cos(data.heading)
						let headingX1 = Math.sin(data.heading + 0.8 * Math.PI)
						let headingY1 = Math.cos(data.heading + 0.8 * Math.PI)
						let headingX2 = Math.sin(data.heading - 0.8 * Math.PI)
						let headingY2 = Math.cos(data.heading - 0.8 * Math.PI)
						replay.context.moveTo(pos.x + scale * replay.boidSize * headingX, pos.y + scale * replay.boidSize * headingY)
						replay.context.lineTo(pos.x + scale * replay.boidSize * headingX1, pos.y + scale * replay.boidSize * headingY1)
						replay.context.lineTo(pos.x + scale * replay.boidSize * headingX2, pos.y + scale * replay.boidSize * headingY2)
						replay.context.closePath()
					} else {
						replay.context.arc(pos.x, pos.y, replay.boidSize * scale, 0, Math.PI, false)
					}

					replay.context.fill()
			}
		});
		
		if (this.selected) {
			let pos = replay.convertCoords(this.frame[this.selected].position.x, this.frame[this.selected].position.y)
			this.context.beginPath()			
			this.context.lineWidth=scale * 0.4;
			this.context.strokeStyle="#FFFFFF";
			this.context.arc(pos.x, pos.y, replay.boidSize * scale, 0, 2 * Math.PI, false)
			this.context.stroke()
			this.context.font = Math.trunc(scale * 8) + 'px arial'
			this.context.fillText(Replay.decodeUnicode(this.frame[this.selected].name), 0, scale * 8)
			this.context.lineWidth=scale * 0.2;
			this.context.strokeStyle="#000000";
			this.context.strokeText(Replay.decodeUnicode(this.frame[this.selected].name), 0, scale * 8)
		}
		
	}
		
	static decodeUnicode(s) {
		return decodeURIComponent(JSON.parse('"' + s + '"'));
	}
	
	getScale() {
		return 30 * this.imageDst.width / Math.abs(this.coords.width);
	}
	
	calcDstBox() {
		let imageScale = (this.imageSrc.right - this.imageSrc.left) / (this.imageSrc.bottom - this.imageSrc.top);
		let canvasScale = this.canvas.width / this.canvas.height;
		let offsetX = 0
		let offsetY = 0
		let width = 0
		let height = 0
		if (canvasScale > imageScale) {
			width = Math.trunc(imageScale * this.canvas.height);
			height = this.canvas.height;
			offsetX = Math.trunc((this.canvas.width - width) / 2.0)
		} else {
			width = this.canvas.width;
			height = Math.trunc(1 / imageScale * this.canvas.width);
			offsetY = Math.trunc((this.canvas.height - height) / 2.0)
		}		
		return new AreaBox(offsetX, offsetX + width, offsetY, offsetY + height)
	}

	convertCoords(x, y) {
		return new Point(
			(x - this.coords.left) / this.coords.width * this.imageDst.width + this.imageDst.left,
			(y - this.coords.top) / this.coords.height * this.imageDst.height + this.imageDst.top
		)
	}
	
	distSqrd(x1, y1, x2, y2) {
		return (x2 - x1)*(x2 - x1) + (y2 - y1)*(y2 - y1);
	}
	
	clicked(x, y) {
		let rangeSqrd = this.getScale() * this.getScale() * this.dotSize * this.dotSize;
		let closest = null;
		let closestDist = rangeSqrd;
		let replay = this;
		$.each(this.frame, function(name, data) {
			let pos = replay.convertCoords(data.position.x, data.position.y)
			let relDist = replay.distSqrd(pos.x,pos.y,x, y)
			if (relDist < closestDist) {
				closest = name;
				closestDist = relDist;
			}
		});
		
		this.selected = closest;
		
		if (!this.playing) {
			this.renderFrame();
		}
	}
	
	
	static deltaTrackCalculator(time, frameData) {
		let target = Replay.generatePath(frameData, this.path)
		let item = this.path[this.path.length - 1]
		if (this.data[this.data.length - 1].time < time) {
			target[item] = this.data[this.data.length - 1].value
		} else if (time > this.data[0].time){
			let firstIndex = 0;
			while (this.data[firstIndex].time < time) {
				firstIndex++;
			}
			let timeRange = this.data[firstIndex].time - this.data[firstIndex - 1].time
			let t = (time - this.data[firstIndex - 1].time) / timeRange;
			
			target[item] = this.sampleFunc(this.data[firstIndex - 1].value, this.data[firstIndex].value, t)
		}
	}

	static seriesTrackCalculator(time, frameData) {
		let target = Replay.generatePath(frameData, this.path)
		let item = this.path[this.path.length - 1]
				
		if (time > this['end-time']) {
			target[item] = this.data[this.data.length - 1]
		} else if (time > this['start-time']){
			let normalisedTime = (time - this['start-time']) / this['frequency']
			let startIndex = Math.trunc(normalisedTime)
			let endIndex = Math.ceil(normalisedTime)
			let startValue = this.data[Math.trunc(normalisedTime)]
			targetItem = this.sampleFunc(this.data[startIndex], this.data[endIndex], normalisedTime - startIndex)
		}
	}
	
	static floor(a, b, t) {
		return a
	}
	
	static lerp(a, b, t) {
		return a + (b - a) * t
	}
	
	static slerp(a, b, t) {
		if (a - b > Math.PI) {
			let result = Replay.lerp(a, b + 2 * Math.PI, t) 
			if (result > 2 * Math.PI) {
				result -= 2 * Math.PI
			}
			return result
		} else if (b - a > Math.PI) {
			let result = Replay.lerp(a + 2 * Math.PI, b, t) 
			if (result > 2 * Math.PI) {
				result -= 2 * Math.PI
			}
			return result
		} else {
			return Replay.lerp(a, b, t)
		}
	}

	static printTime(time) {
		return Math.trunc(time / 60) + ':' + Replay.stringPadLeft(Math.trunc(time % 60), '0', 2);
	}

	static stringPadLeft(str, pad, length) {
		return (new Array(length+1).join(pad)+str).slice(-length);
	}
	
	// Given a path (a list of strings) creates an object chain in object corresponding to the path for any part that is missing, minus the last value in the path. Returns the end object.
	// The intended use is along the lines of
	//
	// target = generatePath(root, path);
	// target[path[path.length - 1]] = value;
	//
	// To insert a value at the end of the path.
	static generatePath(object, path) {
		let target = object
		$.each(path.slice(0, path.length - 1), function(index, part) {
			if (!(part in target)) {
				target[part] = {}
			}
			target = target[part]
		});
		return target;
	}
	
}

