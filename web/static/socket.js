window.init = function(){
    "use strict";

    var wson = WSON(ws_addr);
    let last_keep_alive = Date.now();

    let song_offset_el = document.getElementById("song_offset");
    let song_start_el = document.getElementById("song_start");
    let song_duration_el = document.getElementById("song_duration");

    song_start_el.value = new Date(Date.now() - parseInt(song_offset_el.value) * 1000).getTime();

    function on_update(data) {
        if (data.artist.length > 0)
            document.getElementById("title").innerText = data.artist + " - " + data.title;
        else
            document.getElementById("title").innerText = data.title;

        song_duration_el.value = data.duration;
        song_offset_el.value = 3
        song_start_el.value = Date.now();
    }

    function on_keep_alive() {
        last_keep_alive = Date.now();
    }

    setTimeout(function(){
        var time_delta = Date.now() - last_keep_alive;
        if (time_delta.minute > 3){
            location.reload();
        } else {
            console.log("Alive: OK");
        }
    }, 60000);

    wson.on("update", on_update);
    wson.on("keep_alive", on_keep_alive);
};
