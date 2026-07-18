from flask import Flask, jsonify, request, render_template_string
import time


app = Flask(__name__)

# Render keeps these points in memory.
# They are erased whenever Render restarts or redeploys.
trail_points = []
known_point_ids = set()

MAX_TRAIL_POINTS = 10000


def normalise_optional_float(value):
    if value in (None, "", "None"):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalise_point(data):
    """
    Validate and standardise a GPS point received from the Raspberry Pi.
    """

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        raise ValueError("Missing latitude or longitude")

    latitude = float(latitude)
    longitude = float(longitude)

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")

    timestamp = float(data.get("timestamp", time.time()))
    device = str(data.get("device", "mappi"))

    # New Pi scripts send a UUID as point_id.
    # This fallback also supports older saved CSV points.
    point_id = str(
        data.get("point_id")
        or f"{device}-{timestamp:.6f}-{latitude:.7f}-{longitude:.7f}"
    )

    return {
        "point_id": point_id,
        "device": device,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": timestamp,
        "speed_knots": normalise_optional_float(data.get("speed_knots")),
        "course": normalise_optional_float(data.get("course")),
    }


def store_point(point):
    """
    Add a point unless it is already stored.
    Returns True when added and False when it was a duplicate.
    """

    global trail_points
    global known_point_ids

    if point["point_id"] in known_point_ids:
        return False

    trail_points.append(point)
    known_point_ids.add(point["point_id"])

    # Keep points ordered chronologically.
    trail_points.sort(key=lambda item: item["timestamp"])

    # Prevent unlimited memory growth.
    if len(trail_points) > MAX_TRAIL_POINTS:
        removed_points = trail_points[:-MAX_TRAIL_POINTS]
        trail_points = trail_points[-MAX_TRAIL_POINTS:]

        for removed_point in removed_points:
            known_point_ids.discard(removed_point["point_id"])

    return True


@app.route("/")
def map_page():
    return render_template_string(
        """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Mappi GPS Trail</title>

    <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIINfQ3ynhQGgGUqSOMh4KCWNhZZZB9gQpA="
        crossorigin=""
    >

    <style>
        :root {
            --black: #111111;
            --grey: #686868;
            --light-grey: #ecece7;
            --white: rgba(255, 255, 255, 0.88);
            --green: #234c35;
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            width: 100%;
            height: 100%;
            margin: 0;
            overflow: hidden;
            background: #f3f3ef;
            font-family:
                Helvetica,
                "Helvetica Neue",
                Arial,
                sans-serif;
        }

        #map {
            width: 100%;
            height: 100vh;
            background: #f3f3ef;
            filter:
                saturate(0.62)
                contrast(1.04)
                brightness(1.01);
        }

        #info-panel {
            position: absolute;
            top: 18px;
            left: 18px;
            z-index: 1000;

            width: min(310px, calc(100vw - 36px));
            padding: 16px 18px;

            color: var(--black);
            background: var(--white);
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 16px;

            box-shadow:
                0 12px 40px rgba(0, 0, 0, 0.12);

            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }

        .eyebrow {
            margin-bottom: 7px;

            color: var(--grey);
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        #device-name {
            margin: 0 0 13px;

            font-size: 21px;
            font-weight: 500;
            letter-spacing: -0.025em;
        }

        .data-grid {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 5px 14px;

            font-size: 12px;
            line-height: 1.45;
        }

        .data-label {
            color: var(--grey);
        }

        .data-value {
            overflow: hidden;

            color: var(--black);
            text-align: right;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        #status {
            display: flex;
            align-items: center;
            gap: 7px;

            margin-top: 14px;
            padding-top: 11px;

            color: var(--grey);
            border-top: 1px solid rgba(0, 0, 0, 0.08);

            font-size: 10px;
            line-height: 1.4;
        }

        .status-dot {
            flex: 0 0 auto;

            width: 7px;
            height: 7px;

            background: var(--green);
            border-radius: 50%;

            box-shadow:
                0 0 0 4px rgba(35, 76, 53, 0.12);
        }

        .status-dot.waiting {
            background: #777777;
            box-shadow:
                0 0 0 4px rgba(80, 80, 80, 0.12);
        }

        .credit {
            position: absolute;
            bottom: 14px;
            left: 14px;
            z-index: 1000;

            padding: 6px 10px;

            color: #555555;
            background: rgba(255, 255, 255, 0.76);
            border: 1px solid rgba(0, 0, 0, 0.06);
            border-radius: 999px;

            font-size: 9px;
            letter-spacing: 0.06em;
            text-transform: uppercase;

            backdrop-filter: blur(9px);
            -webkit-backdrop-filter: blur(9px);
        }

        .leaflet-control-zoom {
            overflow: hidden;

            border: none !important;
            border-radius: 12px !important;

            box-shadow:
                0 8px 26px rgba(0, 0, 0, 0.13) !important;
        }

        .leaflet-control-zoom a {
            color: var(--black) !important;
            background: rgba(255, 255, 255, 0.9) !important;
            border: none !important;

            font-family: Helvetica, Arial, sans-serif !important;
            font-weight: 400 !important;
        }

        .leaflet-control-zoom a:first-child {
            border-bottom:
                1px solid rgba(0, 0, 0, 0.08) !important;
        }

        .leaflet-popup-content-wrapper {
            color: var(--black);
            border-radius: 14px;

            font-family: Helvetica, Arial, sans-serif;

            box-shadow:
                0 10px 34px rgba(0, 0, 0, 0.16);
        }

        .leaflet-popup-content {
            min-width: 190px;
            margin: 14px 16px;

            font-size: 12px;
            line-height: 1.5;
        }

        .popup-title {
            display: block;
            margin-bottom: 5px;

            font-size: 13px;
            font-weight: 600;
        }

        .popup-muted {
            color: var(--grey);
            font-size: 10px;
        }

        .mappi-icon-container {
            position: relative;

            width: 38px;
            height: 38px;
        }

        .mappi-pulse {
            position: absolute;
            inset: 0;

            background: rgba(35, 76, 53, 0.17);
            border-radius: 50%;

            animation: mappi-pulse 2.4s infinite ease-out;
        }

        .mappi-dot {
            position: absolute;
            top: 10px;
            left: 10px;

            width: 18px;
            height: 18px;

            background: var(--black);
            border: 3px solid white;
            border-radius: 50%;

            box-shadow:
                0 0 0 2px rgba(0, 0, 0, 0.2),
                0 7px 18px rgba(0, 0, 0, 0.26);
        }

        @keyframes mappi-pulse {
            0% {
                transform: scale(0.65);
                opacity: 0.9;
            }

            100% {
                transform: scale(1.7);
                opacity: 0;
            }
        }

        @media (max-width: 600px) {
            #info-panel {
                top: 12px;
                left: 12px;

                width: calc(100vw - 24px);
                padding: 14px 16px;
            }

            #device-name {
                font-size: 18px;
            }

            .credit {
                bottom: 12px;
                left: 12px;
            }

            .leaflet-top.leaflet-right {
                top: 126px;
            }
        }
    </style>
</head>

<body>
    <div id="map"></div>

    <section id="info-panel">
        <div class="eyebrow">Live GPS trail</div>

        <h1 id="device-name">Mappi</h1>

        <div class="data-grid">
            <div class="data-label">Latitude</div>
            <div class="data-value" id="latitude">—</div>

            <div class="data-label">Longitude</div>
            <div class="data-value" id="longitude">—</div>

            <div class="data-label">Trail points</div>
            <div class="data-value" id="point-count">0</div>

            <div class="data-label">Speed</div>
            <div class="data-value" id="speed">—</div>

            <div class="data-label">Last update</div>
            <div class="data-value" id="last-update">—</div>
        </div>

        <div id="status">
            <span
                id="status-dot"
                class="status-dot waiting"
            ></span>

            <span id="status-text">
                Waiting for GPS data
            </span>
        </div>
    </section>

    <div class="credit">
        Mappi · Live position archive
    </div>

    <script
        src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
        crossorigin=""
    ></script>

    <script>
        const map = L.map("map", {
            zoomControl: false,
            attributionControl: false,
            preferCanvas: true
        }).setView([45.0, 9.0], 6);

        L.control.zoom({
            position: "topright"
        }).addTo(map);

        L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/" +
            "rastertiles/voyager/{z}/{x}/{y}{r}.png",
            {
                maxZoom: 20,
                subdomains: "abcd"
            }
        ).addTo(map);

        const mappiIcon = L.divIcon({
            className: "",
            html: `
                <div class="mappi-icon-container">
                    <div class="mappi-pulse"></div>
                    <div class="mappi-dot"></div>
                </div>
            `,
            iconSize: [38, 38],
            iconAnchor: [19, 19],
            popupAnchor: [0, -20]
        });

        let currentMarker = null;
        let trailLine = null;
        let firstSuccessfulLoad = true;

        function isValidCoordinate(value) {
            return (
                value !== null &&
                value !== undefined &&
                value !== "" &&
                Number.isFinite(Number(value))
            );
        }

        function formatTimestamp(timestamp) {
            if (!timestamp) {
                return "Unknown";
            }

            const date = new Date(Number(timestamp) * 1000);

            if (Number.isNaN(date.getTime())) {
                return "Unknown";
            }

            return date.toLocaleString();
        }

        function formatSpeed(knots) {
            if (
                knots === null ||
                knots === undefined ||
                knots === ""
            ) {
                return "—";
            }

            const speedKnots = Number(knots);

            if (!Number.isFinite(speedKnots)) {
                return "—";
            }

            const kilometresPerHour = speedKnots * 1.852;

            return kilometresPerHour.toFixed(1) + " km/h";
        }

        function updateInformationPanel(latest, count) {
            document.getElementById("device-name").textContent =
                latest.device || "Mappi";

            document.getElementById("latitude").textContent =
                Number(latest.latitude).toFixed(6);

            document.getElementById("longitude").textContent =
                Number(latest.longitude).toFixed(6);

            document.getElementById("point-count").textContent =
                String(count);

            document.getElementById("speed").textContent =
                formatSpeed(latest.speed_knots);

            document.getElementById("last-update").textContent =
                formatTimestamp(latest.timestamp);

            document
                .getElementById("status-dot")
                .classList.remove("waiting");

            document.getElementById("status-text").textContent =
                "Receiving GPS data";
        }

        function setWaitingMessage(message) {
            document
                .getElementById("status-dot")
                .classList.add("waiting");

            document.getElementById("status-text").textContent =
                message;
        }

        function updateTrailLayer(points) {
            const coordinates = points
                .filter(point =>
                    isValidCoordinate(point.latitude) &&
                    isValidCoordinate(point.longitude)
                )
                .map(point => [
                    Number(point.latitude),
                    Number(point.longitude)
                ]);

            if (coordinates.length === 0) {
                return;
            }

            if (!trailLine) {
                trailLine = L.polyline(coordinates, {
                    color: "#111111",
                    weight: 3,
                    opacity: 0.78,
                    lineCap: "round",
                    lineJoin: "round",
                    smoothFactor: 1
                }).addTo(map);
            } else {
                trailLine.setLatLngs(coordinates);
            }
        }

        function updateLatestMarker(latest) {
            const latitude = Number(latest.latitude);
            const longitude = Number(latest.longitude);

            if (!currentMarker) {
                currentMarker = L.marker(
                    [latitude, longitude],
                    {
                        icon: mappiIcon,
                        keyboard: true
                    }
                ).addTo(map);
            } else {
                currentMarker.setLatLng([
                    latitude,
                    longitude
                ]);
            }

            currentMarker.bindPopup(`
                <span class="popup-title">
                    ${latest.device || "Mappi"}
                </span>

                ${latitude.toFixed(6)},
                ${longitude.toFixed(6)}
                <br>

                <span class="popup-muted">
                    Updated
                    ${formatTimestamp(latest.timestamp)}
                </span>
            `);
        }

        function frameTrail(points, latest) {
            if (!firstSuccessfulLoad) {
                return;
            }

            const coordinates = points
                .filter(point =>
                    isValidCoordinate(point.latitude) &&
                    isValidCoordinate(point.longitude)
                )
                .map(point => [
                    Number(point.latitude),
                    Number(point.longitude)
                ]);

            if (coordinates.length > 1) {
                const bounds = L.latLngBounds(coordinates);

                map.fitBounds(bounds, {
                    padding: [50, 50],
                    maxZoom: 16
                });
            } else {
                map.setView(
                    [
                        Number(latest.latitude),
                        Number(latest.longitude)
                    ],
                    16,
                    {
                        animate: true
                    }
                );
            }

            firstSuccessfulLoad = false;
        }

        async function updateMap() {
            try {
                const response = await fetch(
                    "/trail",
                    {
                        cache: "no-store"
                    }
                );

                if (!response.ok) {
                    throw new Error(
                        "Server returned " + response.status
                    );
                }

                const data = await response.json();
                const points = Array.isArray(data.trail)
                    ? data.trail
                    : [];

                const latest = data.latest;

                if (
                    !latest ||
                    !isValidCoordinate(latest.latitude) ||
                    !isValidCoordinate(latest.longitude)
                ) {
                    setWaitingMessage(
                        "Waiting for GPS data"
                    );
                    return;
                }

                updateTrailLayer(points);
                updateLatestMarker(latest);
                updateInformationPanel(
                    latest,
                    data.count ?? points.length
                );
                frameTrail(points, latest);

            } catch (error) {
                console.error(error);

                setWaitingMessage(
                    "Could not load GPS data"
                );
            }
        }

        updateMap();

        window.setInterval(
            updateMap,
            10000
        );
    </script>
</body>
</html>
        """
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "trail_points": len(trail_points),
        }
    )


@app.route("/location", methods=["GET"])
def location():
    latest = trail_points[-1] if trail_points else {
        "device": "mappi",
        "latitude": None,
        "longitude": None,
        "timestamp": None,
        "speed_knots": None,
        "course": None,
    }

    return jsonify(latest)


@app.route("/trail", methods=["GET"])
def trail():
    latest = trail_points[-1] if trail_points else {
        "device": "mappi",
        "latitude": None,
        "longitude": None,
        "timestamp": None,
        "speed_knots": None,
        "course": None,
    }

    return jsonify(
        {
            "latest": latest,
            "trail": trail_points,
            "count": len(trail_points),
        }
    )


@app.route("/update-location", methods=["POST"])
def update_location():
    data = request.get_json(silent=True)

    if not data:
        return jsonify(
            {
                "status": "error",
                "error": "No JSON received",
            }
        ), 400

    try:
        point = normalise_point(data)
    except (TypeError, ValueError) as error:
        return jsonify(
            {
                "status": "error",
                "error": str(error),
            }
        ), 400

    added = store_point(point)

    return jsonify(
        {
            "status": "ok",
            "added": added,
            "point_id": point["point_id"],
            "trail_points": len(trail_points),
        }
    )


@app.route("/upload-trail", methods=["POST"])
def upload_trail():
    """
    Receive several stored CSV points from the Raspberry Pi.
    Existing point IDs are ignored rather than duplicated.
    """

    data = request.get_json(silent=True) or {}
    points = data.get("points", [])

    if not isinstance(points, list):
        return jsonify(
            {
                "status": "error",
                "error": "'points' must be a list",
            }
        ), 400

    accepted_ids = []
    errors = []
    added_count = 0

    for index, raw_point in enumerate(points):
        try:
            point = normalise_point(raw_point)
            added = store_point(point)

            accepted_ids.append(point["point_id"])

            if added:
                added_count += 1

        except (TypeError, ValueError) as error:
            errors.append(
                {
                    "index": index,
                    "error": str(error),
                }
            )

    return jsonify(
        {
            "status": "ok",
            "received": len(points),
            "added": added_count,
            "accepted_ids": accepted_ids,
            "errors": errors,
            "trail_points": len(trail_points),
        }
    )


@app.route("/clear-trail", methods=["POST"])
def clear_trail():
    trail_points.clear()
    known_point_ids.clear()

    return jsonify(
        {
            "status": "ok",
            "message": "Trail cleared",
            "trail_points": 0,
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
    )