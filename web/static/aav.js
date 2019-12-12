(function(){
    var fft, amplitude, source;
    var audio_el;
    var song_start_el;
    var song_duration_el;

    var dots = [];
    var numDots = 250;
    var dot_ttl = 100;

    var prev_volume = 0;

    var waveform_buffer = [];
    var waveform_buffer_len = 1024;
    for (var i = 0; i < waveform_buffer_len; i ++) {
        waveform_buffer.push(0);
    }

    var wavelog_buffer = [];
    var wavelog_buffer_len = 512;
    for (var i = 0; i < wavelog_buffer_len; i ++) {
        wavelog_buffer.push(0);
    }

    var baseline_first, baseline_second;
    var waveform_height, wavelog_height;

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

        baseline_first = 0.625 * windowHeight;
        baseline_second = 0.365 * windowHeight;
        waveform_height = 0.1 * windowHeight;
        wavelog_height = 0.16 * windowHeight;

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
        background(volume - prev_volume > 0.2 ? 60 : volume - prev_volume > 0.1 ? 30 : 0);

        push();
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
        noFill();
        strokeWeight(5);
        volume > 0.4 ? stroke(6,173,227,210) : stroke(127,125,161,210);
        beginShape();
        vertex(0, baseline_first);
        for (var i = 0; i < waveform_buffer_len; i ++) {
            vertex(
                map(i, 0, waveform_buffer_len, 0, width),
                baseline_first - waveform_buffer[i] * waveform_height / parseFloat(audio_el.volume)
            );
        }
        vertex(width, baseline_first);
        endShape();
        pop();

        if (volume > 0) {
            wavelog_buffer.shift();
            wavelog_buffer.push(volume);
        }

        push();
        noStroke();
        fill(127,125,161,80);
        beginShape();
        vertex(0, baseline_second);
        for (var i = 0; i < wavelog_buffer_len; i ++) {
            vertex(
                map(i, 0, wavelog_buffer_len, 0, width),
                baseline_second - wavelog_buffer[i] * wavelog_height
            );
        }
        vertex(width, baseline_second);
        for (var i = wavelog_buffer_len - 1; i >= 0 ; i --) {
            vertex(
                map(i, 0, wavelog_buffer_len, 0, width),
                baseline_second + wavelog_buffer[i] * wavelog_height
            );
        }
        vertex(0, baseline_second);
        endShape();
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
        this.y = baseline_first;
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
        baseline_first = 0.625 * windowHeight;
        baseline_second = 0.365 * windowHeight;
        waveform_height = 0.1 * windowHeight;
        wavelog_height = 0.16 * windowHeight;
    }

    window.preload = preload;
    window.setup = setup;
    window.draw = draw;
    window.windowResized = windowResized;
})();