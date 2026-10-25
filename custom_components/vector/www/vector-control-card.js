/*
 * Vector — control card: camera stream and driving the robot.
 *
 *   type: custom:vector-control-card
 *   camera: camera.vector            # required
 *   speed: 120                       # mm/s forward (optional)
 *   hold: true                       # take control while the card is open (default: true)
 *
 * While open, the card holds behavior control (the "Manual control" switch, renewed every 5 min):
 * Vector stands still and waits for commands. When the card closes, control returns to Vector.
 * Buttons are hold-to-drive: the card calls vector.move every 300 ms and the robot stops
 * 0.7 s after the last call (also when the network drops or the window closes). The camera stream
 * closes with the card — the add-on then stops the camera and gives control back to Vector.
 */
(function () {
  "use strict";
  var CARD_VERSION = "0.1.2";
  var REPEAT_MS = 300;
  var HOLD_RENEW_MS = 5 * 60 * 1000; // the add-on holds control for at most 10 min

  var STYLE =
    ":host{display:block}" +
    "ha-card{overflow:hidden}" +
    ".cam{position:relative;background:#000;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center}" +
    ".cam img{width:100%;height:100%;object-fit:contain;display:block}" +
    ".cam .msg{position:absolute;color:#ccc;font-size:.9em;text-align:center;padding:8px;display:flex;flex-direction:column;align-items:center;gap:10px}" +
    ".cam .msg:empty{display:none}" +
    ".cam .msg button{padding:6px 14px;font-size:.95em}" +
    ".charger{display:none;align-items:center;justify-content:center;gap:10px;margin:10px 16px 0;padding:10px 12px;" +
    "border-radius:12px;background:rgba(28,230,160,.12);color:var(--primary-text-color);font-size:.9em;flex-wrap:wrap}" +
    ".charger.on{display:flex}" +
    ".charger button{padding:8px 14px;background:#1ce6a0;color:#000;font-weight:600;gap:6px}" +
    ".charger ha-icon{--mdc-icon-size:20px}" +
    ".status{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;padding:8px 12px 0;font-size:.85em;color:var(--secondary-text-color)}" +
    ".status b{color:var(--primary-text-color);font-weight:600}" +
    ".pad{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:center;padding:12px 16px 16px}" +
    ".col{display:flex;flex-direction:column;align-items:center;gap:8px}" +
    ".col .lbl{font-size:.8em;color:var(--secondary-text-color)}" +
    ".dpad{display:grid;grid-template-columns:repeat(3,64px);grid-template-rows:repeat(3,64px);gap:6px}" +
    "button{all:unset;box-sizing:border-box;display:flex;align-items:center;justify-content:center;" +
    "border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);" +
    "cursor:pointer;touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;" +
    "transition:background .1s,transform .1s}" +
    "button.hold{width:64px;height:64px}" +
    "button.small{width:56px;height:52px}" +
    "button.active{background:var(--primary-color);color:var(--text-primary-color,#fff);transform:scale(.95)}" +
    "button.stop{background:var(--error-color,#db4437);color:#fff;width:64px;height:64px;font-weight:700}" +
    "ha-icon{--mdc-icon-size:30px;pointer-events:none}" +
    ".actions{display:flex;gap:8px;justify-content:center;padding:0 16px 16px;flex-wrap:wrap}" +
    ".actions button{padding:8px 14px;font-size:.9em;gap:6px}" +
    ".actions ha-icon{--mdc-icon-size:20px}" +
    ".speed{display:flex;gap:4px;justify-content:center;padding:0 16px 12px}" +
    ".speed button{padding:4px 12px;font-size:.8em;border-radius:10px}" +
    ".speed button.on{background:var(--primary-color);color:var(--text-primary-color,#fff)}" +
    ".speed .sep{width:12px}" +
    ".speed button.hold-t{gap:6px}" +
    ".speed button.hold-t ha-icon{--mdc-icon-size:16px}" +
    ".speed button.hold-t.on{background:#1ce6a0;color:#000}";

  var SPEEDS = { slow: 0.5, normal: 1, fast: 1.6 };

  var I18N = {
    en: {
      head: "Head",
      lift: "Lift",
      slow: "Slow",
      normal: "Normal",
      fast: "Fast",
      hold: "Hold",
      holding: "Holding",
      drive_off: "Drive off charger",
      to_charger: "Go to charger",
      snapshot: "Refresh snapshot",
      on_charger: "Vector is on the charger.",
      battery: "Battery",
      doing: "Doing:",
      off_charger: "off the charger",
      connecting: "Connecting to the camera…",
      unavailable: "Vector is unavailable",
      no_camera: "The camera is not responding. If this keeps happening, restart Vector.",
      retry: "Try again",
      config_error: "Set camera: camera.vector",
      card_name: "Vector — control",
      card_description: "Vector camera stream and driving: forward, back, turn, head and lift.",
    },
    pl: {
      head: "Głowa",
      lift: "Ramię",
      slow: "Wolno",
      normal: "Normalnie",
      fast: "Szybko",
      hold: "Trzymaj",
      holding: "Trzymam",
      drive_off: "Zjedź z ładowarki",
      to_charger: "Do ładowarki",
      snapshot: "Zdjęcie do podglądu",
      on_charger: "Vector stoi na ładowarce.",
      battery: "Bateria",
      doing: "Robi:",
      off_charger: "poza ładowarką",
      connecting: "Łączenie z kamerą…",
      unavailable: "Vector jest niedostępny",
      no_camera: "Kamera nie odpowiada. Jeśli to się powtarza, zrestartuj Vectora.",
      retry: "Spróbuj ponownie",
      config_error: "Ustaw camera: camera.vector",
      card_name: "Vector — sterowanie",
      card_description: "Podgląd z kamery Vectora i jazda: przód, tył, skręt, głowa i ramię.",
    },
  };

  // UI language: from hass when available, otherwise from the page; anything but Polish → English.
  function language(hass) {
    var lang =
      (hass && ((hass.locale && hass.locale.language) || hass.language)) ||
      (document.documentElement && document.documentElement.lang) ||
      "en";
    return String(lang).toLowerCase().indexOf("pl") === 0 ? "pl" : "en";
  }

  function tr(hass, key) {
    return I18N[language(hass)][key] || I18N.en[key] || key;
  }

  function createCardClass() {
    return class VectorControlCard extends window.HTMLElement {
      setConfig(config) {
        if (!config || !config.camera) throw new Error(tr(this._hass, "config_error"));
        this._config = config;
        this._speed = "normal";
        this._built = false;
      }

      getCardSize() {
        return 9;
      }

      static getStubConfig() {
        return { camera: "camera.vector" };
      }

      set hass(hass) {
        this._hass = hass;
        if (!this._built) this._build();
        this._update();
      }

      connectedCallback() {
        if (this._built) {
          this._startStream();
          this._autoHold();
        }
      }

      disconnectedCallback() {
        this._stopHold();
        this._stopStream();
        clearInterval(this._holdRenew);
        this._holdRenew = undefined;
        if (this._weHold) this._setHold(false);
      }

      _t(key) {
        return tr(this._hass, key);
      }

      // The robot "Manual control" switch (translation_key hold_control).
      _holding() {
        var sw = this._sibling("switch", "hold_control");
        return !!sw && sw.state === "on";
      }

      _setHold(on) {
        var sw = this._sibling("switch", "hold_control");
        if (!sw) return;
        this._weHold = on;
        clearInterval(this._holdRenew);
        this._holdRenew = undefined;
        this._hass.callService("switch", on ? "turn_on" : "turn_off", { entity_id: sw.entity_id });
        if (on) {
          var self = this;
          this._holdRenew = setInterval(function () {
            if (self.isConnected) self._hass.callService("switch", "turn_on", { entity_id: sw.entity_id });
          }, HOLD_RENEW_MS);
        }
      }

      _autoHold() {
        if (this._config.hold === false || this._weHold || this._holding()) return;
        if (this._sibling("switch", "hold_control")) this._setHold(true);
      }

      _deviceId() {
        var ent = this._hass && this._hass.entities && this._hass.entities[this._config.camera];
        return ent ? ent.device_id : undefined;
      }

      // Entity of the same robot, found by translation_key in the registry (independent of names
      // and language); "battery" = the sensor with device_class battery (it has no translation_key).
      _sibling(domain, key) {
        var dev = this._deviceId();
        var ents = (this._hass && this._hass.entities) || {};
        for (var id in ents) {
          var e = ents[id];
          if (e.device_id !== dev || e.platform !== "vector" || id.indexOf(domain + ".") !== 0) continue;
          var st = this._hass.states[id];
          if (!st) continue;
          if (key === "battery" ? st.attributes.device_class === "battery" : e.translation_key === key) return st;
        }
        return undefined;
      }

      _build() {
        var root = this.shadowRoot || this.attachShadow({ mode: "open" });
        var t = this._t.bind(this);
        root.innerHTML =
          "<style>" + STYLE + "</style>" +
          "<ha-card>" +
          '<div class="cam"><img alt=""><div class="msg"></div></div>' +
          '<div class="charger"><span>' + t("on_charger") + "</span>" +
          '<button data-press="drive_off_charger"><ha-icon icon="mdi:arrow-up-box"></ha-icon>' + t("drive_off") + "</button></div>" +
          '<div class="status"></div>' +
          '<div class="pad">' +
          '<div class="col"><span class="lbl">' + t("head") + "</span>" +
          '<button class="hold small" data-head="1"><ha-icon icon="mdi:arrow-up-bold"></ha-icon></button>' +
          '<button class="hold small" data-head="-1"><ha-icon icon="mdi:arrow-down-bold"></ha-icon></button></div>' +
          '<div class="dpad">' +
          "<span></span>" +
          '<button class="hold" data-drive="fwd"><ha-icon icon="mdi:chevron-up"></ha-icon></button>' +
          "<span></span>" +
          '<button class="hold" data-drive="left"><ha-icon icon="mdi:rotate-left"></ha-icon></button>' +
          '<button class="stop" data-stop="1">STOP</button>' +
          '<button class="hold" data-drive="right"><ha-icon icon="mdi:rotate-right"></ha-icon></button>' +
          "<span></span>" +
          '<button class="hold" data-drive="back"><ha-icon icon="mdi:chevron-down"></ha-icon></button>' +
          "<span></span>" +
          "</div>" +
          '<div class="col"><span class="lbl">' + t("lift") + "</span>" +
          '<button class="hold small" data-lift="1"><ha-icon icon="mdi:arrow-up-bold"></ha-icon></button>' +
          '<button class="hold small" data-lift="-1"><ha-icon icon="mdi:arrow-down-bold"></ha-icon></button></div>' +
          "</div>" +
          '<div class="speed">' +
          '<button data-speed="slow">' + t("slow") + "</button>" +
          '<button data-speed="normal">' + t("normal") + "</button>" +
          '<button data-speed="fast">' + t("fast") + "</button>" +
          '<span class="sep"></span><button class="hold-t"><ha-icon icon="mdi:hand-back-right"></ha-icon><span>' + t("hold") + "</span></button>" +
          "</div>" +
          '<div class="actions">' +
          '<button data-press="drive_off_charger"><ha-icon icon="mdi:arrow-up-box"></ha-icon>' + t("drive_off") + "</button>" +
          '<button data-press="drive_on_charger"><ha-icon icon="mdi:battery-charging"></ha-icon>' + t("to_charger") + "</button>" +
          '<button data-press="refresh_camera"><ha-icon icon="mdi:camera-retake"></ha-icon>' + t("snapshot") + "</button>" +
          "</div>" +
          "</ha-card>";
        this._root = root;
        this._img = root.querySelector(".cam img");
        this._msg = root.querySelector(".cam .msg");
        this._status = root.querySelector(".status");
        var self = this;

        root.querySelectorAll("button.hold").forEach(function (btn) {
          btn.addEventListener("pointerdown", function (ev) {
            ev.preventDefault();
            if (btn.setPointerCapture) btn.setPointerCapture(ev.pointerId);
            self._startHold(btn);
          });
          ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (name) {
            btn.addEventListener(name, function () {
              self._stopHold();
            });
          });
          btn.addEventListener("contextmenu", function (ev) {
            ev.preventDefault();
          });
        });
        root.querySelector("button.stop").addEventListener("click", function () {
          self._stopHold();
          self._call("stop", {});
        });
        root.querySelectorAll(".speed button[data-speed]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            self._speed = btn.dataset.speed;
            self._update();
          });
        });
        root.querySelector(".speed .hold-t").addEventListener("click", function () {
          self._setHold(!self._holding());
        });
        root.querySelectorAll(".actions button, .charger button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            self._pressButton(btn.dataset.press);
          });
        });
        // Stream broken (the robot camera sends no frames; the add-on closes the stream after 30 s).
        this._img.addEventListener("error", function () {
          self._showRetry(self._t("no_camera"));
        });
        this._img.addEventListener("load", function () {
          self._msg.textContent = "";
        });
        this._built = true;
        this._startStream();
        this._autoHold();
      }

      _startStream() {
        var cam = this._hass && this._hass.states[this._config.camera];
        if (!cam || !this._img) return;
        var token = cam.attributes.access_token;
        // multipart MJPEG through HA (signed with the camera token); ~2 fps
        this._img.src = "/api/camera_proxy_stream/" + this._config.camera + "?token=" + token + "&t=" + Date.now();
        this._msg.textContent = this._t("connecting");
        this._streamToken = token;
      }

      _showRetry(text) {
        var self = this;
        this._msg.innerHTML = "";
        var p = document.createElement("span");
        p.textContent = text;
        var b = document.createElement("button");
        b.textContent = this._t("retry");
        b.addEventListener("click", function () {
          self._startStream();
        });
        this._msg.appendChild(p);
        this._msg.appendChild(b);
      }

      _onCharger() {
        var ch = this._sibling("binary_sensor", "on_charger");
        return ch && ch.state === "on";
      }

      _stopStream() {
        if (this._img) this._img.removeAttribute("src");
        this._streamToken = undefined;
      }

      _vector(base) {
        var f = this._config.speed || 120;
        var k = SPEEDS[this._speed] || 1;
        var v = Math.round(f * k);
        switch (base) {
          case "fwd":
            return { left: v, right: v };
          case "back":
            return { left: -Math.round(v * 0.8), right: -Math.round(v * 0.8) };
          case "left":
            return { left: -Math.round(v * 0.6), right: Math.round(v * 0.6) };
          case "right":
            return { left: Math.round(v * 0.6), right: -Math.round(v * 0.6) };
        }
        return {};
      }

      _startHold(btn) {
        this._stopHold(true);
        // "forward" on the charger = drive off it (Vector leaves the station himself)
        if (btn.dataset.drive === "fwd" && this._onCharger()) {
          this._pressButton("drive_off_charger");
          return;
        }
        var data;
        if (btn.dataset.drive) data = this._vector(btn.dataset.drive);
        else if (btn.dataset.head) data = { head: Number(btn.dataset.head) * 1.2 };
        else if (btn.dataset.lift) data = { lift: Number(btn.dataset.lift) * 1.5 };
        if (!data) return;
        btn.classList.add("active");
        this._holdBtn = btn;
        var self = this;
        this._call("move", data);
        this._holdTimer = setInterval(function () {
          self._call("move", data);
        }, REPEAT_MS);
      }

      _stopHold(silent) {
        if (this._holdTimer) {
          clearInterval(this._holdTimer);
          this._holdTimer = undefined;
          if (!silent) this._call("move", {});
        }
        if (this._holdBtn) {
          this._holdBtn.classList.remove("active");
          this._holdBtn = undefined;
        }
      }

      _call(service, data) {
        if (!this._hass) return;
        var dev = this._deviceId();
        var payload = Object.assign({}, data);
        if (dev) payload.device_id = dev;
        this._hass.callService("vector", service, payload).catch(function (err) {
          console.warn("vector." + service, err && err.message);
        });
      }

      _pressButton(key) {
        var st = this._sibling("button", key);
        if (st) this._hass.callService("button", "press", { entity_id: st.entity_id });
      }

      _update() {
        if (!this._built || !this._hass) return;
        var cam = this._hass.states[this._config.camera];
        if (cam && cam.attributes.access_token !== this._streamToken && this.isConnected) this._startStream();
        if (!cam || cam.state === "unavailable") this._msg.textContent = this._t("unavailable");
        var parts = [];
        var bat = this._sibling("sensor", "battery");
        if (bat) parts.push(this._t("battery") + " <b>" + bat.state + " %</b>");
        var act = this._sibling("sensor", "activity");
        if (act && act.state !== "unknown") parts.push(this._t("doing") + " <b>" + act.state + "</b>");
        var charger = this._sibling("binary_sensor", "on_charger");
        if (charger && charger.state !== "on") parts.push(this._t("off_charger"));
        this._root.querySelector(".charger").classList.toggle("on", !!charger && charger.state === "on");
        this._status.innerHTML = parts.join(" · ");
        var self = this;
        this._root.querySelectorAll(".speed button[data-speed]").forEach(function (b) {
          b.classList.toggle("on", b.dataset.speed === self._speed);
        });
        var held = this._holding();
        var ht = this._root.querySelector(".speed .hold-t");
        ht.classList.toggle("on", held);
        ht.querySelector("span").textContent = this._t(held ? "holding" : "hold");
        if (!this._triedHold && this._sibling("switch", "hold_control")) {
          this._triedHold = true;
          this._autoHold();
        }
      }
    };
  }

  // Extra modules (add_extra_js_url) load before the scoped CustomElementRegistry polyfill,
  // so the card is only registered once <home-assistant> exists.
  function registerCard() {
    var registry = window.customElements;
    if (registry.get("vector-control-card")) return;
    registry.define("vector-control-card", createCardClass());
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "vector-control-card",
      name: tr(null, "card_name"),
      description: tr(null, "card_description"),
      documentationURL: "https://github.com/witold-gren/home-assistant-vector-integration",
    });
    console.info("%c VECTOR-CONTROL-CARD %c " + CARD_VERSION + " ", "background:#1ce6a0;color:#000", "");
  }

  (function waitForFrontend(attempt) {
    if (window.customElements.get("home-assistant") || attempt >= 600) {
      registerCard();
      return;
    }
    setTimeout(function () {
      waitForFrontend(attempt + 1);
    }, 50);
  })(0);
})();
