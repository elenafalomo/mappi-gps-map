from flask import Flask, request, jsonify, render_template_string
import time

app = Flask(__name__)

latest_location = {
    "device": "mappi",
    "latitude": None,
    "longitude": None,
    "timestamp": None,
    "speed_knots": None,
    "course": None,
}

trail_points = []

MAX_TRAIL_POINTS = 1000


@app.route("/")
def map_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Mappi GPS Tracker</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        html, body {
            margin: 0;
            height: 100%;
            font-family: Helvetica, Arial, sans-serif;
            background: #f5f5f2;
        }

        #map {
            height: 100vh;
            width: 100%;
            filter: saturate(0.55) contrast(1.05);
        }

        #info {
            position: absolute;
            top: 18px;
            left: 18px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.86);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            padding: 14px 16px;
            border-radius: 14px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
            font-size: 13px;
            line-height: 1.45;
            color: #111;
            min-width: 230px;
            border: 1px solid rgba(0,0,0,0.08);
        }

        #info strong {
            font-size: 14px;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }

        #status {
            font-size: 11px;
            color: #666;
            margin-top: 8px;
        }

        .credit {
            position: absolute;
            bottom: 14px;
            left: 14px;
            z-index: 1000;
            font-size: 10px;
            letter-spacing: 0.02em;
            color: #555;
            background: rgba(255,255,255,0.72);
            padding: 5px 8px;
            border-radius: 999px;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border: 1px solid rgba(0,0,0,0.06);
        }

        .leaflet-control-zoom {
            border: none !important;
            box-shadow: 0 6px 18px rgba(0,0,0,0.12) !important;
        }

        .leaflet-control-zoom a {
            background: rgba(255,255,255,0.88) !important;
            color: #111 !important;
            border: none !important;
            font-family: Helvetica, Arial, sans-serif;
        }

        .leaflet-popup-content-wrapper {
            border-radius: 14px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.16);
            font-family: Helvetica, Arial, sans-serif;
        }

        .leaflet-popup-content {
            font-size: 13px;
            line-height: 1.45;
        }

        .mappi-marker-pulse {
            position: relative;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: rgba(20, 70, 40, 0.18);
            animation: pulse 2.2s infinite;
        }

        .mappi-marker {
            position: absolute;
            top: 9px;
            left: 9px;
            width: 18px;
            height: 18px;
            background: #111;
            border: 3px solid #ffffff;
            border-radius: 50%;
            box-sizing: border-box;
            box-shadow:
                0 0 0 2px rgba(0,0,0,0.25),
                0 8px 20px rgba(0,0,0,0.25);
        }

        @keyframes pulse {
            0% {
                transform: scale(0.7);
                opacity: 0.75;
            }
            100% {
                transform: scale(1.6);
                opacity: 0;
            }
        }

        @media (max-width: 600px) {
            #info {
                top: 12px;
                left: 12px;
                right: 12px;
                min-width: auto;
            }

            .credit {
                left: 12px;
                bottom: 12px;
            }
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
        <strong>Mappi</strong><br>
        Waiting for GPS position...
        <div id="status"></div>
    </div>

    <div id="map"></div>

    <div class="credit">Live GPS trail · Mappi</div>

    <script>
        const map = L.map('map', {
            zoomControl: false,
            attributionControl: false
        }).setView([45.0, 12.0], 6);

        L.control.zoom({
            position: 'topright'
        }).addTo(map);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            maxZoom: 19
        }).addTo(map);

        let marker = null;
        let trailLine = null;
        let firstFix = true;

        const mappiIcon = L.divIcon({
            className: '',
            html: `
                <div class="mappi-marker-pulse">
                    <div class="mappi-marker"></div>
                </div>
            `,
            iconSize: [36, 36],
            iconAnchor: [18, 18],
            popupAnchor: [0, -18]
        });

        function formatTimestamp(ts) {
            if (!ts) return "unknown";

            const numericTs = Number(ts);
            const date = new Date(numericTs * 1000);

            if (isNaN(date.getTime())) {
                return "unknown";
            }

            return date.toLocaleString();
        }

        async function updateMap() {
            try {
                const response = await fetch('/trail');
                const data = await response.json();

                const latest = data.latest;
                const trail = data.trail || [];

                if (latest.latitude && latest.longitude) {
                    const lat = Number(latest.latitude);
                    const lon = Number(latest.longitude);

                    const trailLatLngs = trail
                        .filter(p => p.latitude && p.longitude)
                        .map(p => [Number(p.latitude), Number(p.longitude)]);

                    if (trailLatLngs.length > 1) {
                        if (!trailLine) {
                            trailLine = L.polyline(trailLatLngs, {
                                color: "#111",
                                weight: 3,
                                opacity: 0.72,
                                lineCap: "round",
                                lineJoin: "round"
                            }).addTo(map);
                        } else {
                            trailLine.setLatLngs(trailLatLngs);
                        }
                    }

                    if (!marker) {
                        marker = L.marker([lat, lon], {
                            icon: mappiIcon
                        }).addTo(map);
                    } else {
                        marker.setLatLng([lat, lon]);
                    }

                    if (firstFix) {
                        map.setView([lat, lon], 16, {
                            animate: true,
                            duration: 1.2
                        });
                        firstFix = false;
                    }

                    marker.bindPopup(
                        `<strong>${latest.device || "mappi"}</strong><br>
                        ${lat.toFixed(6)}, ${lon.toFixed(6)}<br>
                        <span style="color:#666;">Updated ${formatTimestamp(latest.timestamp)}</span>`
                    );

                    document.getElementById("info").innerHTML =
                        `<strong>${latest.device || "mappi"}</strong><br>
                        Latitude&nbsp;&nbsp; ${lat.toFixed(6)}<br>
                        Longitude&nbsp; ${lon.toFixed(6)}<br>
                        Trail points&nbsp; ${trail.length}
                        <div id="status">Last update: ${formatTimestamp(latest.timestamp)}</div>`;
                } else {
                    document.getElementById("status").innerText =
                        "Waiting for GPS fix.";
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


@app.route("/location", methods=["GET"])
def location():
    return jsonify(latest_location)


@app.route("/trail", methods=["GET"])
def trail():
    return jsonify({
        "latest": latest_location,
        "trail": trail_points
    })


@app.route("/update-location", methods=["POST"])
def update_location():
    global latest_location
    global trail_points

    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({"error": "Missing latitude or longitude"}), 400

    point = {
        "device": data.get("device", "mappi"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "timestamp": data.get("timestamp", time.time()),
        "speed_knots": data.get("speed_knots"),
        "course": data.get("course"),
    }

    latest_location = point
    trail_points.append(point)

    if len(trail_points) > MAX_TRAIL_POINTS:
        trail_points = trail_points[-MAX_TRAIL_POINTS:]

    print("Updated location:", latest_location)
    print("Trail points:", len(trail_points))

    return jsonify({
        "status": "ok",
        "location": latest_location,
        "trail_points": len(trail_points)
    })


@app.route("/clear-trail", methods=["POST"])
def clear_trail():
    global trail_points

    trail_points = []

    return jsonify({
        "status": "ok",
        "message": "Trail cleared"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
