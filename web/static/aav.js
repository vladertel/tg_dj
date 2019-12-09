(function(){
    var fft, amplitude, source;
    var audio_el;
    var song_start_el;
    var song_duration_el;

    var dots = [];
    var numDots = 250;
    var rotation = 0;
    var rotation_speed = 0;

    var dot_x_min = 70;
    var dot_x_max = 400;
    var dot_ttl = 100;

    var line_offset = 120;
    var line_length = 255;

    var prev_volume = 0;

    var waveform_buffer = [];
    var waveform_buffer_len = 1024;
    for (var i = 0; i < waveform_buffer_len; i ++) {
        waveform_buffer.push(0);
    }

    function preload() {
        var audioCtx = getAudioContext();
        audio_el = document.getElementById('stream');
        source = audioCtx.createMediaElementSource(audio_el);
        source.connect(p5.soundOut);

        song_start_el = document.getElementById("song_start");
        song_duration_el = document.getElementById("song_duration");
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
            var x_start = random(0,windowWidth);
            var v_start = random(1.4, 1.5) * (random(-1,1) > 0 ? 1 : -1);
            dots[i] = new Dot(x_start, v_start);
        }
    }


    function draw() {

        var volume = amplitude.getLevel() / parseFloat(audio_el.volume);
        var spectrum = fft.analyze(128);

        background(volume - prev_volume > 0.2 ? 60 : volume - prev_volume > 0.1 ? 30 : 0);

        push();

//        strokeWeight(10);
//        volume > 0.4 ? stroke(127,125,161,170) : stroke(6,173,227,170);
//
//        var len = 128;
//        var dir_num = 160;
//
//        for (var i = 0; i < len; i++) {
//            var angle = map(i % dir_num, 0, dir_num, 0, 34 * PI);
//            var line_end = line_offset + spectrum[i] * line_length / 255;
//            line(
//                line_offset * sin(angle),
//                line_offset * cos(angle),
//                line_end * sin(angle),
//                line_end * cos(angle)
//            );
//        }

        for (var i = 0; i < dots.length; ++i) {
            if (dots[i].move(volume)) {
                dots[i].draw(volume);
            } else {
                delete dots[i];
                var x_start = random(0,windowWidth);
                var v_start = volume * 80 * random(0.5, 1.5) * (random(-1,1) > 0 ? 1 : -1);
                dots[i] = new Dot(x_start, v_start);
                dots[i].draw(volume);
            }
        }

        pop();

        var wave_len = 1024;
        var wave_parts_num = 1024;
        var waveform = fft.waveform(wave_len).slice(0,wave_len);
        for (var j = 0; j < wave_parts_num; j ++) {
            var waveform_part = waveform.slice(wave_len * j / wave_parts_num, wave_len * (j + 1) / wave_parts_num);
            var waveform_part_avg = waveform_part.reduce((a,b) => a + b, 0) / waveform_part.length
            waveform_buffer.shift();
            waveform_buffer.push(waveform_part_avg);
        }

        push();
        strokeWeight(5);
        volume > 0.4 ? stroke(6,173,227,210) : stroke(127,125,161,210);
        for (var i = 0; i < waveform_buffer_len - 1; i ++) {
            var x1 = map(i, 0, waveform_buffer_len, 0, width);
            var x2 = map(i + 1, 0, waveform_buffer_len, 0, width);
            line(
                x1, 300 - waveform_buffer[i] * 100 / parseFloat(audio_el.volume),
                x2, 300 - waveform_buffer[i + 1] * 100 / parseFloat(audio_el.volume)
            );
        }
        pop();

        var song_progress;
        var duration = parseInt(song_duration_el.value);
        if (duration === 0) {
            song_progress = 0;
        } else {
            song_progress = (Date.now() - parseInt(song_start_el.value)) / parseInt(duration) / 1000;
        }
        if (song_progress > 1) song_progress = 1;

        push();
        strokeWeight(10);
        noFill();
        stroke(127,125,161,210);
        line(0, 5, map(song_progress, 0, 1, 0, windowWidth), 5);
        pop();

        prev_volume = volume;
    }



    function Dot(x, speedY) {
        this.x = x;
        this.y = 300;
        this.speedY = speedY;
        this.ttl = dot_ttl;

        this.size = random(1,7);
    }

    Dot.prototype.draw = function(volume) {
        var size = this.size;

        if (random(1) > 0.995) {
            var multiplier = volume > 0.3 ? random(100,250) : 30;
            size = volume * multiplier;
        }

        this.color1 = color(127,125,161, map(this.ttl, 0, dot_ttl, 0, 255));
        this.color2 = color(6,173,227, map(this.ttl, 0, dot_ttl, 0, 255));

        noStroke();
        volume > 0.4 ? fill(this.color2) : fill(this.color1);
        ellipse(this.x, this.y, size, size);
    };

    Dot.prototype.move = function() {
        this.ttl -= 1;
        this.y += this.speedY;

        if ( this.y > windowHeight || this.y < 0 || this.ttl < 0 ) {
            return false
        } else {
            return true
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
    window.windowResized = windowResized;
})();