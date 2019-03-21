window.init = function(){
    "use strict";

    if (ws_addr === "auto") {
        ws_addr = "ws://" + window.location.host + window.location.pathname + "ws"
    }

    var wson = WSON(ws_addr);
    let last_keep_alive = Date.now();

    let song_offset_el = document.getElementById("song_offset");
    let song_start_el = document.getElementById("song_start");
    let song_duration_el = document.getElementById("song_duration");

    song_start_el.value = new Date(Date.now() - parseInt(song_offset_el.value) * 1000).getTime();

    function on_update(data) {
        setTimeout(function(){
            if (data.artist.length > 0)
                document.getElementById("title").innerText = data.artist + " - " + data.title;
            else
                document.getElementById("title").innerText = data.title;

            song_duration_el.value = data.duration;
            song_offset_el.value = 0;
            song_start_el.value = Date.now();
        }, 3000)

        check_lag();
    }

    function on_keep_alive() {
        last_keep_alive = Date.now();
    }

    setInterval(function(){
        var time_delta = Date.now() - last_keep_alive;
        if (time_delta.minute > 3){
            location.reload();
        } else {
            console.log("Alive: OK");
        }
    }, 60000);

    wson.on("update", on_update);
    wson.on("keep_alive", on_keep_alive);

    ////////////

    var start_time = (new Date()).getTime();
    var initial_lag = null;
    var audio_el = document.getElementById('stream');
    var play_btn = document.getElementById("logo");

    audio_el.oncanplaythrough = function() {
        audio_el.muted = true;
        audio_el.play();

        play_btn.onclick = function(e){
            audio_el.muted = false;
            audio_el.volume = audio_volume;
        };

        play_btn.style.opacity = "1"

        initial_lag = get_lag();
        console.log("Initial lag: " + initial_lag);
    }

    function check_lag() {
        if (initial_lag === null) return;
        var lag = get_lag();
        if (lag - initial_lag > 1) {
            audio_el.currentTime = audio_el.buffered.end(0)-1;
            console.log("Lag NOK: " + (lag - initial_lag));
        } else {
            console.log("Lag OK: " + (lag - initial_lag));
        }
    }

    function get_lag() {
        var buf_size = audio_el.buffered.end(0) - audio_el.buffered.start(0);
        var time_elapsed = ((new Date()).getTime() - start_time) / 1000;
        return time_elapsed - buf_size;
    }

    function get_cookie(name) {
        var matches = document.cookie.match(new RegExp(
            "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
        ));
        return matches ? decodeURIComponent(matches[1]) : undefined;
    }

    var volume_cookie_name = "dj_volume";
    var audio_volume = get_cookie(volume_cookie_name);
    if (typeof audio_volume === "undefined")
        audio_volume = 0.05

    function set_volume(value) {
        audio_el.volume = audio_volume = value;
        document.cookie = (volume_cookie_name + "=" + value + "; path=/");
    }

    window.set_volume = set_volume;
};
