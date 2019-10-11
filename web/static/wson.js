/**
 * WebSocket JSON-based messages handler
 * @param address
 * @return {WSON}
 * @constructor
 */
function WSON(address){
    var ws = null;
    var handlers = {};
    var requests = {};
    var open_handlers = [];
    var close_handlers = [];

    function init(){
        console.log("WS connection init...");
        var connection_timeout = setTimeout(() => ws.close(), 10000);
        ws = new WebSocket(address);
        ws.onopen = function () {
            clearTimeout(connection_timeout);
            console.log("WS connection established");
            for (var i = 0; i < open_handlers.length; i++){
                open_handlers[i]();
            }
        };
        ws.onmessage = on_message;
        ws.onclose = function () {
            clearTimeout(connection_timeout);
            console.log("WS connection closed");
            for (var i = 0; i < close_handlers.length; i++){
                close_handlers[i]();
            }
            setTimeout(init, 1000);
        };
        ws.onerror = function (err) {
            clearTimeout(connection_timeout);
            console.log("WS error: ", err);
            ws.close();
        };
    }

    init();

    function on_message(event){
        console.log(event.data);

        var data = event.data;
        var msg_arr = JSON.parse(data);
        var names = Object.keys(msg_arr);

        for (var i = 0; i < names.length; i++){
            var name = names[i];
            if (name in handlers){
                handlers[name](msg_arr[name]);
            }

            if (name in requests){
                requests[name](msg_arr[name]);
                delete requests[name];
            }
        }
    };

    this.onopen = function(handler){
        open_handlers.push(handler);
    };
    this.onclose = function(handler){
        close_handlers.push(handler);
    };

    this.on = function(msg, handler){
        handlers[msg] = handler;
    };
    this.off = function(msg){
        delete handlers[msg];
    };

    this.fetch = function(msg, args = {}){
        return new Promise(resolve => {
            requests[msg] = function(a){
                resolve(a);
            };
            this.send(msg, args);
        });
        // TODO: promise never resolves if server respond with an error
    };

    this.send = function(msg, data){
        data = data || {};
        var o = {};
        o[msg] = data;
        ws.send(JSON.stringify(o));
    };

    return this;
}
