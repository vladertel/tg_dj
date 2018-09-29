/**
 * WebSocket JSON-based messages handler
 * @param address
 * @return {WSON}
 * @constructor
 */
function WSON(address){
    var ws = new WebSocket(address);
    var handlers = {};
    var requests = {};

    ws.onmessage = function(event){
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
        ws.onopen = handler;
    };
    this.onclose = function(handler){
        ws.onclose = handler;
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
