from flask import Flask, request, jsonify, render_template_string
import time

app = Flask(__name__)

latest_location = {
    "device": "mappi",
    "latitude": None,
    "longitude": None,
    "timestamp": None,
    "speed_knots": None,
    "course": None
}


@app.route("/update-location", methods=["POST"])
def update_location():
    global latest_location

    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({"error": "Missing latitude or longitude"}), 400

    latest_location = {
        "device": data.get("device", "mappi"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "timestamp": data.get("timestamp", time.time()),
        "speed_knots": data.get("speed_knots"),
        "course": data.get("course")
    }

    print("Updated location:", latest_location)

    return jsonify({
        "status": "ok",
        "location": latest_location
    })


@app.route("/location", methods=["GET"])
def location():
    return jsonify(latest_location)


@app.route("/")
def map_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Mappi GPS Tracker</title>
    <meta charset="utf-8" />

    <style>
        html, body {
            margin: 0;
            height: 100%;
            font-family: Arial, sans-serif;
        }

        #map {
            height: 100vh;
            width: 100%;
        }

        #info {
            position: absolute;
            top: 12px;
            left: 12px;
            z-index: 1000;
            background: white;
            padding: 12px 14px;
            border-radius: 10px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.25);
            font-size: 14px;
            line-height: 1.4;
        }

        #status {
            font-size: 12px;
            color: #666;
            margin-top: 6px;
        }
    </style>

    <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet/dist/leaflet.css"
    />

    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
</head>

<body>
    <div id="info">
        <strong>Mappi GPS Tracker</strong><br>
        Waiting for GPS position...
        <div id="status"></div>
    </div>

    <div id="map"></div>

    <script>
        const map = L.map('map').setView([45.0, 12.0], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        let marker = null;
        let firstFix = true;

        function formatTimestamp(ts) {
            if (!ts) return "unknown";
            const date = new Date(ts * 1000);
            return date.toLocaleString();
        }

        async function updateMap() {
            try {
                const response = await fetch('/location');
                const data = await response.json();

                if (data.latitude && data.longitude) {
                    const lat = data.latitude;
                    const lon = data.longitude;

                    if (!marker) {
                        marker = L.marker([lat, lon]).addTo(map);
                    } else {
                        marker.setLatLng([lat, lon]);
                    }

                    if (firstFix) {
                        map.setView([lat, lon], 16);
                        firstFix = false;
                    }

                    const popupText =
                        "<strong>" + data.device + "</strong><br>" +
                        "Lat: " + lat.toFixed(6) + "<br>" +
                        "Lon: " + lon.toFixed(6) + "<br>" +
                        "Updated: " + formatTimestamp(data.timestamp);

                    marker.bindPopup(popupText);

                    document.getElementById("info").innerHTML =
                        "<strong>" + data.device + "</strong><br>" +
                        "Latitude: " + lat.toFixed(6) + "<br>" +
                        "Longitude: " + lon.toFixed(6) + "<br>" +
                        "<div id='status'>Last update: " + formatTimestamp(data.timestamp) + "</div>";
                } else {
                    document.getElementById("status").innerText =
                        "No GPS fix received yet.";
                }
            } catch (error) {
                document.getElementById("status").innerText =
                    "Could not load location.";
                console.error(error);
            }
        }

        updateMap();
        setInterval(updateMap, 10000);
    </script>
</body>
</html>
    """)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
