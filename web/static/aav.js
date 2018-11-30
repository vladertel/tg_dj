(function(){
    var fft, amplitude, source;
    var myMediaElement;
    var song_start_el;
    var song_duration_el;

    var dots = [];
    var numDots = 250;
    var rotation = 0;

    var dot_x_min = 70;
    var dot_x_max = 400;

    var line_offset = 120;
    var line_length = 255;

    var global_volume = 0.05;

    function preload() {
        var audioCtx = getAudioContext();
        myMediaElement = document.getElementById('stream');
        source = audioCtx.createMediaElementSource(myMediaElement);
        source.connect(p5.soundOut);
        document.getElementById("logo").onclick = function(e){
            myMediaElement.muted = false;
            myMediaElement.volume = global_volume;
        };

        song_start_el = document.getElementById("song_start");
        song_duration_el = document.getElementById("song_duration");
    }

    function set_volume(value) {
        myMediaElement.volume = global_volume = value;
    }

    function setup() {
        createCanvas(windowWidth, windowHeight);
        background(0);
        frameRate(30);
        smooth();
        colorMode(HSB, 255, 255, 255, 255);

        dot_x_max = (windowWidth + windowHeight) * 0.2;
        line_length = (windowWidth + windowHeight) * 0.12;

        amplitude = new p5.Amplitude();
        amplitude.setInput(source);
        fft = new p5.FFT();
        fft.setInput(source);

        for (var i = 0; i < numDots; i++) {
            var x_start = random(dot_x_min,dot_x_max);
            var v_start = random(1.4, 1.5) * (random(-1,1) > 0 ? 1 : -1);
            dots[i] = new Dot(x_start, v_start);
        }
    }


    function draw() {

        var volume = amplitude.getLevel() / global_volume;
        var spectrum = fft.analyze(128);

        background(volume > 0.4 ? 30 : 0);

        push();

        translate(width/2, height/2);
        rotate(rotation);

        strokeWeight(10);
        volume > 0.4 ? stroke(127,125,161,170) : stroke(6,173,227,170);

        var len = 128;
        var dir_num = 160;

        for (var i = 0; i < len; i++) {
            var angle = map(i % dir_num, 0, dir_num, 0, 34 * PI);
            var line_end = line_offset + spectrum[i] * line_length / 255;
            line(
                line_offset * sin(angle),
                line_offset * cos(angle),
                line_end * sin(angle),
                line_end * cos(angle)
            );
        }

        for (var i = 0; i < dots.length; ++i) {
            rotate(radians(360/numDots));
            dots[i].draw(volume);
            dots[i].move(volume);
        }
        rotation = rotation + volume/7;

        pop();

        song_progress = (Date.now() - parseInt(song_start_el.value)) / parseInt(song_duration_el.value) / 1000;
        if (song_progress > 1) song_progress = 1;
        strokeWeight(10);
        noFill();
        stroke(127,125,161,210)
        arc(width/2, height/2, line_offset * 2 - 15, line_offset * 2 - 15, - PI / 2, PI * 2 * song_progress - PI / 2);
    }



    function Dot(x, speedX) {
        this.x = x;
        this.speedX = speedX;

        this.color1 = color(127,125,161, random(200,255));
        this.color2 = color(6,173,227, random(200,255));
        this.size = random(1,7);
    }

    Dot.prototype.draw = function(volume) {
        var size = this.size;

        if (random(1) > 0.995) {
            var multiplier = volume > 0.3 ? random(100,250) : 30;
            size = volume * multiplier;
        }

        noStroke();
        volume > 0.4 ? fill(this.color2) : fill(this.color1);
        ellipse(this.x, 0, size, size);
    };

    Dot.prototype.move = function(volume) {
        this.x += this.speedX * volume * 10;

        if ( this.x > dot_x_max ) {
            this.speedX = -Math.abs(this.speedX);
        } else if ( this.x < dot_x_min ) {
            this.speedX = Math.abs(this.speedX);
        }
    };

    function windowResized() {
        resizeCanvas(windowWidth, windowHeight);
        dot_x_max = (windowWidth + windowHeight) * 0.2;
        line_length = (windowWidth + windowHeight) * 0.12;
    }

    window.preload = preload;
    window.setup = setup;
    window.draw = draw;
    window.set_volume = set_volume;
    window.windowResized = windowResized;
})();