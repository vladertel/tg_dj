var address = "wss://212.86.109.84:8081/ws";

wson = WSON(address)

function on_update(data):
    console.log("got data")
    console.log(data)

function on_keep_alive():
    console.log("got keep_alive")


wson.on("update", on_update)
wson.on("keep_alive", on_keep_alive)