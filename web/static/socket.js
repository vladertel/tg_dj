(function(){
    "use strict";

    var wson = WSON(ws_addr);
    let last_keep_alive = Date.now();

    function on_update(data) {
        document.getElementById("title").innerText = data.title + " - " + data.artist;
        document.getElementById("duration").innerText = data.duration;
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
})();
