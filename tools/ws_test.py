import json
import websocket


def main():
    client = websocket.create_connection("ws://localhost:9999/ws/events")

    info = json.loads(client.recv())
    print("info", info)

    last_idx = info["index"]
    while True:
        client.send(json.dumps(dict(index=last_idx)))

        response = json.loads(client.recv())
        last_idx = response["event"]["index"] + 1
        print("response", response)


main()
