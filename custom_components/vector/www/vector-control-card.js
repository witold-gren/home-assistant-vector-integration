/*
 * Vector — control card: live camera, driving, head and lift, plus a full-screen control view.
 *
 *   type: custom:vector-control-card
 *   camera: camera.vector            # required
 *   speed: 120                       # mm/s forward (optional)
 *   hold: true                       # take control while the card is open (default: true)
 *
 * Behavior control (the "Manual control" switch, renewed every 5 min) is taken while you steer:
 * when the full-screen view opens and at the first drive in the tile; it is given back when the
 * view closes, after a minute without driving, or when the page goes to the background — then
 * Vector goes back to his own things. The "Hold" button keeps it on until pressed again.
 * Buttons are hold-to-drive: the card calls vector.move every 300 ms and the robot stops
 * 0.7 s after the last call (also when the network drops or the window closes); the card also
 * sends an explicit stop on every way a hold can end (release, lost pointer, closing the full
 * screen, the page going to the background, the card being rebuilt).
 *
 * Live view: starts with ▶ (the camera only runs while somebody watches). With add-on 0.2.0+
 * the camera entity has a real stream (H.264 + the robot's microphone, WebRTC through Home
 * Assistant's go2rtc); with older add-ons the card falls back to MJPEG. The live view stops
 * after 5 minutes without a touch and when the page is hidden, so the robot can rest.
 *
 * Full screen (⛶): landscape, the camera fills the screen; driving pad on the left, listening
 * (the robot's microphone), head and lift on the right, speed and charger at the bottom. The view
 * lives in its own element in <body>: dashboards with CSS transforms would otherwise trap
 * position:fixed inside the tile.
 */
(function () {
  "use strict";
  const CARD_VERSION = "0.2.2";
  const REPEAT_MS = 300;
  const HOLD_RENEW_MS = 5 * 60 * 1000; // the add-on holds control for at most 10 min
  const LIVE_IDLE_MS = 5 * 60 * 1000;
  const LIVE_GUARD_TICK_MS = 30 * 1000;
  const FEATURE_STREAM = 2; // CameraEntityFeature.STREAM
  const HOLD_IDLE_MS = 60 * 1000; // give control back this long after the last drive (tile)
  const LIVE_LOAD_MAX_MS = 60 * 1000; // loader until the first frame; then give up
  const DRIVE_OFF_EVERY_MS = 8000; // "forward" on the charger asks to drive off at most this often

  const SPEEDS = { slow: 0.5, normal: 1, fast: 1.6 };

  const I18N = {
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
      unavailable_hint: "Check that Vector is on and connected to Wi-Fi.",
      no_preview: "Camera preview is off",
      no_preview_hint: "Tap ▶ to watch live",
      no_camera: "The camera is not responding. If this keeps happening, restart Vector.",
      retry: "Try again",
      live: "Watch live",
      close_live: "Stop live view",
      fullscreen: "Full-screen control",
      exit_full: "Back",
      start_live: "Start live view",
      listen_on: "Listen to Vector",
      listen_off: "Mute Vector",
      no_audio: "Sound needs the Vector add-on 0.2.0 or newer",
      tap_sound: "Tap 🔊 to hear Vector",
      loading: "Connecting to Vector…",
      live_failed: "Could not start the live view — try again",
      driving_off: "Vector is driving off the charger…",
      live_paused: "Live view paused — tap ▶ to continue",
      rotate: "Turn your phone sideways",
      config_error: "Set camera: camera.vector",
      card_name: "Vector — control",
      card_description: "Vector live camera and driving: forward, back, turn, head and lift; full-screen control.",
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
      unavailable_hint: "Sprawdź, czy Vector jest włączony i połączony z Wi-Fi.",
      no_preview: "Podgląd z kamery jest wyłączony",
      no_preview_hint: "Dotknij ▶, aby oglądać na żywo",
      no_camera: "Kamera nie odpowiada. Jeśli to się powtarza, zrestartuj Vectora.",
      retry: "Spróbuj ponownie",
      live: "Oglądaj na żywo",
      close_live: "Zatrzymaj podgląd",
      fullscreen: "Sterowanie na pełnym ekranie",
      exit_full: "Wstecz",
      start_live: "Włącz podgląd",
      listen_on: "Słuchaj Vectora",
      listen_off: "Wycisz Vectora",
      no_audio: "Dźwięk wymaga dodatku Vector 0.2.0 lub nowszego",
      tap_sound: "Dotknij 🔊, aby słyszeć Vectora",
      loading: "Łączę z Vectorem…",
      live_failed: "Nie udało się uruchomić podglądu — spróbuj ponownie",
      driving_off: "Vector zjeżdża z ładowarki…",
      live_paused: "Podgląd wstrzymany — dotknij ▶, aby wznowić",
      rotate: "Obróć telefon poziomo",
      config_error: "Ustaw camera: camera.vector",
      card_name: "Vector — sterowanie",
      card_description: "Podgląd na żywo z kamery Vectora i jazda: przód, tył, skręt, głowa i ramię; sterowanie na pełnym ekranie.",
    },
  };

  // UI language: from hass when available, otherwise from the page; anything but Polish → English.
  function language(hass) {
    const lang =
      (hass && ((hass.locale && hass.locale.language) || hass.language)) ||
      (document.documentElement && document.documentElement.lang) ||
      "en";
    return String(lang).toLowerCase().indexOf("pl") === 0 ? "pl" : "en";
  }

  function tr(hass, key) {
    return I18N[language(hass)][key] || I18N.en[key] || key;
  }

  function icon(name) {
    return `<ha-icon icon="${name}"></ha-icon>`;
  }

  // A state that carries no value (robot or entity unavailable).
  function noValue(st) {
    return !st || st.state === "unavailable" || st.state === "unknown" || st.state === "";
  }

  const STYLE = `
    :host { display:block; }
    ha-card { overflow:hidden; }
    button { all:unset; box-sizing:border-box; display:flex; align-items:center; justify-content:center;
      border-radius:14px; background:var(--secondary-background-color); color:var(--primary-text-color);
      cursor:pointer; touch-action:none; user-select:none; -webkit-user-select:none; -webkit-touch-callout:none;
      transition:background .1s, transform .1s, opacity .2s; }
    ha-icon { --mdc-icon-size:30px; pointer-events:none; }

    .cam { position:relative; aspect-ratio:4/3; overflow:hidden;
      background:radial-gradient(circle at 30% 25%, #2b3850 0%, #151b26 55%, #0b0f15 100%); }
    .cam .still, .cam .live { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; display:none; }
    .cam .still.on { display:block; filter:brightness(.55); }
    .cam .live { display:block; --video-max-height:none; }
    .cam .ph { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
      justify-content:center; gap:6px; padding:16px; text-align:center; color:#dfe6ee; }
    .cam .ph ha-icon { --mdc-icon-size:44px; opacity:.75; margin-bottom:4px; }
    .cam .ph .t { font-size:1em; font-weight:500; }
    .cam .ph .h { font-size:.82em; color:#aab5c2; }
    .cam .ph button { margin-top:8px; padding:6px 14px; font-size:.9em; border-radius:10px;
      background:rgba(255,255,255,.14); color:#fff; }
    .cam.live-on .ph { display:none; }
    /* robot available: ▶ in the middle, the text below it (no icon under the button) */
    .cam.can-play .ph .ph-ic { display:none !important; }
    .cam.can-play .ph { justify-content:flex-end; padding-bottom:14%; }
    .cam .cam-btn { position:absolute; z-index:2; width:42px; height:42px; border-radius:50%;
      background:rgba(0,0,0,.45); color:#fff; }
    .cam .cam-btn ha-icon { --mdc-icon-size:24px; }
    .cam .play { left:50%; top:50%; width:64px; height:64px; transform:translate(-50%,-70%);
      background:rgba(28,230,160,.30); border:2px solid rgba(255,255,255,.9); box-shadow:0 0 22px rgba(28,230,160,.35); }
    .cam .play ha-icon { --mdc-icon-size:36px; }
    .cam .play:active { transform:translate(-50%,-70%) scale(.94); }
    .cam .close { right:10px; top:10px; display:none; }
    .cam .full { right:10px; bottom:10px; }
    .cam .mute { left:10px; bottom:10px; display:none; }
    .cam.live-on .mute { display:flex; }
    .cam .mute.on { background:rgba(28,230,160,.55); }
    .cam-load { position:absolute; z-index:3; inset:0; display:none; flex-direction:column; align-items:center;
      justify-content:center; gap:10px; color:#e3e8eb; font-size:.85em; pointer-events:none; }
    .cam-load.show { display:flex; }
    .spin { width:34px; height:34px; border-radius:50%; border:3px solid rgba(255,255,255,.25);
      border-top-color:#1ce6a0; animation:vector-spin .9s linear infinite; }
    @keyframes vector-spin { to { transform:rotate(360deg); } }
    .cam-toast { position:absolute; z-index:3; left:50%; bottom:14px; transform:translateX(-50%); max-width:80%;
      padding:6px 12px; border-radius:10px; background:rgba(0,0,0,.72); color:#fff; font-size:.82em;
      text-align:center; opacity:0; transition:opacity .2s; pointer-events:none; }
    .cam-toast.show { opacity:1; }
    .cam.live-on .play { display:none; }
    .cam.live-on .close { display:flex; }

    ha-card.offline .cam .play, ha-card.offline .cam .close { display:none; }
    ha-card.offline .pad, ha-card.offline .speed, ha-card.offline .actions, ha-card.offline .charger {
      opacity:.35; pointer-events:none; }

    .charger { display:none; align-items:center; justify-content:center; gap:10px; margin:10px 16px 0;
      padding:10px 12px; border-radius:12px; background:rgba(28,230,160,.12); color:var(--primary-text-color);
      font-size:.9em; flex-wrap:wrap; }
    .charger.on { display:flex; }
    .charger button { padding:8px 14px; background:#1ce6a0; color:#000; font-weight:600; gap:6px; }
    .charger ha-icon { --mdc-icon-size:20px; }
    .status { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; padding:8px 12px 0;
      font-size:.85em; color:var(--secondary-text-color); }
    .status b { color:var(--primary-text-color); font-weight:600; }
    .pad { display:grid; grid-template-columns:1fr auto 1fr; gap:16px; align-items:center; padding:12px 16px 16px; }
    .col { display:flex; flex-direction:column; align-items:center; gap:8px; }
    .col .lbl { font-size:.8em; color:var(--secondary-text-color); }
    .dpad { display:grid; grid-template-columns:repeat(3,64px); grid-template-rows:repeat(3,64px); gap:6px; }
    button.hold { width:64px; height:64px; }
    button.small { width:56px; height:52px; }
    button.active { background:var(--primary-color); color:var(--text-primary-color,#fff); transform:scale(.95); }
    button.stop { background:var(--error-color,#db4437); color:#fff; width:64px; height:64px; font-weight:700; }
    .actions { display:flex; gap:8px; justify-content:center; padding:0 16px 16px; flex-wrap:wrap; }
    .actions button { padding:8px 14px; font-size:.9em; gap:6px; }
    .actions ha-icon { --mdc-icon-size:20px; }
    .speed { display:flex; gap:4px; justify-content:center; padding:0 16px 12px; }
    .speed button { padding:4px 12px; font-size:.8em; border-radius:10px; }
    .speed button.on { background:var(--primary-color); color:var(--text-primary-color,#fff); }
    .speed .sep { width:12px; }
    .speed button.hold-t { gap:6px; }
    .speed button.hold-t ha-icon { --mdc-icon-size:16px; }
    .speed button.hold-t.on { background:#1ce6a0; color:#000; }
  `;

  // Full-screen view (portal in <body>), sized for a phone in landscape (~874×402 CSS px).
  const FS_STYLE = `
    * { box-sizing:border-box; }
    button { all:unset; box-sizing:border-box; cursor:pointer; display:flex; align-items:center;
      justify-content:center; color:#fff; -webkit-tap-highlight-color:transparent;
      touch-action:none; user-select:none; -webkit-user-select:none; -webkit-touch-callout:none; }
    ha-icon { pointer-events:none; --mdc-icon-size:26px; }

    .fs { position:absolute; inset:0; overflow:hidden; background:#000; color:#fff;
      touch-action:none; user-select:none; -webkit-user-select:none; -webkit-touch-callout:none;
      font-family:var(--ha-font-family-body, Roboto, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
      /* distance from the edge = safe area (island/notch) + a small margin */
      --edgeL: max(16px, calc(env(safe-area-inset-left, 0px) + 4px));
      --edgeR: max(16px, calc(env(safe-area-inset-right, 0px) + 4px));
      --edgeT: max(8px, env(safe-area-inset-top, 0px));
      --edgeB: max(10px, env(safe-area-inset-bottom, 0px));
      --accent: #1ce6a0; }
    /* the island is on one side only: safe area there, close to the edge on the other */
    .fs.island-left { --edgeR: 20px; }
    .fs.island-right { --edgeL: 20px; }

    .fs-cam { position:absolute; inset:0;
      background:radial-gradient(circle at 30% 25%, #2b3850 0%, #151b26 55%, #0b0f15 100%); }
    .fs-still { position:absolute; inset:0; background:transparent center / cover no-repeat; filter:brightness(.5); }
    .fs-live { position:absolute; inset:0; width:100%; height:100%; display:block; object-fit:cover;
      --video-max-height:none; }
    .fs-grad { position:absolute; inset:0; pointer-events:none; background:linear-gradient(180deg,
      rgba(0,0,0,.45) 0%, rgba(0,0,0,0) 24%, rgba(0,0,0,0) 70%, rgba(0,0,0,.55) 100%); }
    .fs-ui { position:absolute; inset:0; }

    .fs-rotate { position:absolute; inset:0; z-index:10; display:none; flex-direction:column;
      align-items:center; justify-content:center; gap:14px; padding:24px; text-align:center;
      background:#000; color:#cfd6da; font-size:1rem; }
    .fs-rotate ha-icon { --mdc-icon-size:52px; opacity:.8; }
    .fs.portrait .fs-rotate { display:flex; }
    .fs.portrait .fs-ui { display:none; }

    .fs-topl { position:absolute; z-index:4; top:var(--edgeT); left:max(14px, calc(var(--edgeL) - 18px));
      height:56px; display:flex; align-items:center; gap:14px; }
    .fs-back { width:38px; height:38px; border-radius:50%; border:2px solid rgba(255,255,255,.92);
      background:rgba(0,0,0,.2); }
    .fs-back:active { transform:scale(.92); }
    .fs-clock, .fs-batt { font-size:.9rem; font-variant-numeric:tabular-nums; text-shadow:0 1px 3px rgba(0,0,0,.85); }
    .fs-batt { display:flex; align-items:center; gap:2px; opacity:.9; }
    .fs-batt ha-icon { --mdc-icon-size:18px; }

    .fs-play { position:absolute; z-index:5; top:50%; left:50%; transform:translate(-50%,-50%);
      flex-direction:column; gap:10px; }
    .fs-play-ic { width:78px; height:78px; padding-left:4px; border-radius:50%; display:flex;
      align-items:center; justify-content:center; background:rgba(28,230,160,.32);
      border:2px solid rgba(255,255,255,.9); box-shadow:0 0 28px rgba(28,230,160,.4); transition:transform .1s; }
    .fs-play-ic ha-icon { --mdc-icon-size:42px; }
    .fs-play:active .fs-play-ic { transform:scale(.95); }
    .fs-play-lbl { font-size:.85rem; text-shadow:0 1px 4px #000; }

    .fs-load { position:absolute; z-index:5; top:50%; left:50%; transform:translate(-50%,-50%); display:none;
      flex-direction:column; align-items:center; gap:12px; font-size:.85rem; color:#e3e8eb;
      text-shadow:0 1px 4px #000; pointer-events:none; }
    .fs-load.show { display:flex; }
    .spin { width:44px; height:44px; border-radius:50%; border:3px solid rgba(255,255,255,.25);
      border-top-color:var(--accent); animation:vector-spin .9s linear infinite; }
    @keyframes vector-spin { to { transform:rotate(360deg); } }
    .fs-off { position:absolute; z-index:5; top:50%; left:50%; transform:translate(-50%,-50%);
      display:none; flex-direction:column; align-items:center; gap:6px; text-align:center;
      padding:16px 22px; border-radius:16px; background:rgba(0,0,0,.55); max-width:60vw; }
    .fs-off ha-icon { --mdc-icon-size:40px; opacity:.8; }
    .fs-off .h { font-size:.8rem; color:#c5ced8; }
    .fs.offline .fs-off { display:flex; }
    .fs.offline .fs-play { display:none; }
    .fs.offline .fs-pad, .fs.offline .fs-rail, .fs.offline .fs-bottom { opacity:.35; pointer-events:none; }

    /* left: driving pad (forward, back, turn, stop) right next to the island */
    .fs-pad { position:absolute; z-index:4; left:var(--edgeL); top:50%; transform:translateY(-46%);
      display:grid; grid-template-columns:repeat(3,58px); grid-template-rows:repeat(3,58px); gap:6px; }
    .fs-btn { width:58px; height:58px; border-radius:16px; background:rgba(0,0,0,.38);
      border:2px solid rgba(255,255,255,.55); transition:background .1s, transform .1s, border-color .1s; }
    .fs-btn ha-icon { --mdc-icon-size:30px; }
    .fs-btn.active { background:rgba(28,230,160,.55); border-color:var(--accent); transform:scale(.94);
      box-shadow:0 0 16px rgba(28,230,160,.45); }
    .fs-stop { width:58px; height:58px; border-radius:50%; background:#e5483d; border:2px solid rgba(255,255,255,.85);
      font-weight:700; font-size:.8rem; letter-spacing:.5px; }
    .fs-stop:active { transform:scale(.92); }

    /* right: listening (microphone), head and lift on one axis */
    .fs-rail { position:absolute; z-index:4; right:var(--edgeR); top:calc(var(--edgeT) + 6px);
      bottom:var(--edgeB); width:60px; display:flex; flex-direction:column; align-items:center;
      justify-content:space-between; gap:8px; }
    .fs-ic { width:46px; height:46px; border-radius:50%; background:rgba(0,0,0,.36); }
    .fs-ic ha-icon { --mdc-icon-size:24px; }
    .fs-mute.muted { color:#ff6a5f; }
    .fs-mute.listening { background:rgba(28,230,160,.4); }
    .fs-mute.disabled { opacity:.4; }
    .fs-group { display:flex; flex-direction:column; align-items:center; gap:4px; }
    .fs-lbl { font-size:.68rem; color:#e3e8eb; text-shadow:0 1px 3px #000; }
    .fs-pill { width:56px; display:flex; flex-direction:column; overflow:hidden; border-radius:999px;
      border:2px solid rgba(255,255,255,.75); background:rgba(0,0,0,.32); }
    .fs-pill button { width:100%; height:50px; transition:background .1s; }
    .fs-pill button + button { border-top:1px solid rgba(255,255,255,.22); }
    .fs-pill button.active { background:rgba(28,230,160,.5); }

    /* bottom: speed and charger in one translucent pill */
    .fs-bottom { position:absolute; z-index:4; left:50%; bottom:var(--edgeB); transform:translateX(-50%);
      display:flex; align-items:center; gap:4px; padding:5px; border-radius:16px;
      background:rgba(28,30,34,.58); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); }
    .fs-bottom button { height:34px; padding:0 12px; border-radius:11px; font-size:.8rem; gap:6px; }
    .fs-bottom button.on { background:rgba(28,230,160,.85); color:#000; }
    .fs-bottom ha-icon { --mdc-icon-size:20px; }
    .fs-bottom .sep { width:1px; height:22px; margin:0 4px; background:rgba(255,255,255,.25); }

    .fs-toast { position:absolute; z-index:8; top:28%; left:50%; transform:translate(-50%,-50%);
      max-width:70vw; padding:10px 18px; border-radius:12px; background:rgba(0,0,0,.78);
      font-size:.9rem; text-align:center; opacity:0; transition:opacity .2s; pointer-events:none; }
    .fs-toast.show { opacity:1; }
  `;

  function createCardClass() {
    return class VectorControlCard extends window.HTMLElement {
      setConfig(config) {
        if (!config || !config.camera) throw new Error(tr(this._hass, "config_error"));
        // Rebuilding mid-drive (dashboard edit, config change) must not leave the robot moving.
        this._releaseControls();
        this._stopLive();
        if (this._fsOpen) this._closeFull();
        this._config = config;
        this._speed = this._speed || "normal";
        this._built = false;
        if (this._hass) {
          this._build();
          this._update();
        }
      }

      getCardSize() {
        return 9;
      }

      static getStubConfig() {
        return { camera: "camera.vector" };
      }

      set hass(hass) {
        this._hass = hass;
        if (!this._config) return;
        if (!this._built) this._build();
        this._update();
        if (this._fsLive && "hass" in this._fsLive) this._fsLive.hass = hass;
        if (this._live && "hass" in this._live) this._live.hass = hass;
      }

      connectedCallback() {
        if (!this._onPageHide) {
          // App in the background / tab hidden / window closed: stop driving and the live view.
          this._onPageHide = () => {
            if (document.visibilityState === "hidden" || document.hidden) {
              this._releaseControls();
              this._pauseLive(false);
              this._releaseAutoHold();
            }
          };
          this._onPageLeave = () => {
            this._releaseControls();
            this._pauseLive(false);
            this._releaseAutoHold();
          };
        }
        document.addEventListener("visibilitychange", this._onPageHide);
        window.addEventListener("pagehide", this._onPageLeave);
      }

      disconnectedCallback() {
        document.removeEventListener("visibilitychange", this._onPageHide);
        window.removeEventListener("pagehide", this._onPageLeave);
        this._releaseControls();
        this._stopLive();
        if (this._fsOpen) this._closeFull();
        this._stopLiveGuard();
        clearInterval(this._holdRenew);
        this._holdRenew = undefined;
        clearTimeout(this._holdIdle);
        if (this._weHold) this._setHold(false);
      }

      _t(key) {
        return tr(this._hass, key);
      }

      /* ---------------- entities ---------------- */

      _camState() {
        return this._hass && this._config ? this._hass.states[this._config.camera] : undefined;
      }

      _offline() {
        const cam = this._camState();
        return !cam || cam.state === "unavailable";
      }

      _hasStream() {
        const cam = this._camState();
        return !!cam && ((cam.attributes.supported_features || 0) & FEATURE_STREAM) !== 0;
      }

      _deviceId() {
        const ent = this._hass && this._hass.entities && this._hass.entities[this._config.camera];
        return ent ? ent.device_id : undefined;
      }

      // Entity of the same robot, found by translation_key in the registry (independent of names
      // and language); "battery" = the sensor with device_class battery (it has no translation_key).
      _sibling(domain, key) {
        const dev = this._deviceId();
        const ents = (this._hass && this._hass.entities) || {};
        for (const id in ents) {
          const e = ents[id];
          if (e.device_id !== dev || e.platform !== "vector" || id.indexOf(domain + ".") !== 0) continue;
          const st = this._hass.states[id];
          if (!st) continue;
          if (key === "battery" ? st.attributes.device_class === "battery" : e.translation_key === key) return st;
        }
        return undefined;
      }

      _onCharger() {
        const ch = this._sibling("binary_sensor", "on_charger");
        return !!ch && ch.state === "on";
      }

      /* ---------------- behavior control ("Manual control" switch) ---------------- */

      _holding() {
        const sw = this._sibling("switch", "hold_control");
        return !!sw && sw.state === "on";
      }

      _setHold(on) {
        const sw = this._sibling("switch", "hold_control");
        if (!sw) return;
        this._weHold = on;
        clearInterval(this._holdRenew);
        this._holdRenew = undefined;
        this._callRaw("switch", on ? "turn_on" : "turn_off", { entity_id: sw.entity_id });
        if (on) {
          this._holdRenew = setInterval(() => {
            if (this.isConnected) this._callRaw("switch", "turn_on", { entity_id: sw.entity_id });
          }, HOLD_RENEW_MS);
        }
      }

      // Take control for steering (full screen opened, first drive in the tile).
      _autoHold() {
        if (!this._config || this._config.hold === false || this._offline()) return;
        if (!this._weHold && !this._holding() && this._sibling("switch", "hold_control")) {
          this._setHold(true);
        }
        this._holdTouch();
      }

      // Each drive extends the hold; in the tile it ends a minute after the last one.
      _holdTouch() {
        clearTimeout(this._holdIdle);
        if (!this._weHold || this._manualHold || this._fsOpen) return;
        this._holdIdle = setTimeout(() => this._releaseAutoHold(), HOLD_IDLE_MS);
      }

      _releaseAutoHold() {
        clearTimeout(this._holdIdle);
        if (this._weHold && !this._manualHold) this._setHold(false);
      }

      /* ---------------- tile ---------------- */

      _build() {
        const root = this.shadowRoot || this.attachShadow({ mode: "open" });
        const t = this._t.bind(this);
        root.innerHTML =
          `<style>${STYLE}</style>` +
          `<ha-card>` +
          `<div class="cam">` +
          `<img class="still" alt="">` +
          `<div class="ph"><ha-icon class="ph-ic" icon="mdi:camera-off-outline"></ha-icon>` +
          `<span class="t"></span><span class="h"></span></div>` +
          `<button class="cam-btn play" title="${t("live")}">${icon("mdi:play")}</button>` +
          `<button class="cam-btn close" title="${t("close_live")}">${icon("mdi:close")}</button>` +
          `<button class="cam-btn full" title="${t("fullscreen")}">${icon("mdi:fullscreen")}</button>` +
          `<button class="cam-btn mute" title="${t("listen_on")}">${icon("mdi:volume-off")}</button>` +
          `<div class="cam-load"><span class="spin"></span><span>${t("loading")}</span></div>` +
          `<div class="cam-toast"></div>` +
          `</div>` +
          `<div class="charger"><span>${t("on_charger")}</span>` +
          `<button data-press="drive_off_charger">${icon("mdi:arrow-up-box")}${t("drive_off")}</button></div>` +
          `<div class="status"></div>` +
          `<div class="pad">` +
          `<div class="col"><span class="lbl">${t("head")}</span>` +
          `<button class="hold small" data-head="1">${icon("mdi:arrow-up-bold")}</button>` +
          `<button class="hold small" data-head="-1">${icon("mdi:arrow-down-bold")}</button></div>` +
          `<div class="dpad">` +
          `<span></span><button class="hold" data-drive="fwd">${icon("mdi:chevron-up")}</button><span></span>` +
          `<button class="hold" data-drive="left">${icon("mdi:rotate-left")}</button>` +
          `<button class="stop" data-stop="1">STOP</button>` +
          `<button class="hold" data-drive="right">${icon("mdi:rotate-right")}</button>` +
          `<span></span><button class="hold" data-drive="back">${icon("mdi:chevron-down")}</button><span></span>` +
          `</div>` +
          `<div class="col"><span class="lbl">${t("lift")}</span>` +
          `<button class="hold small" data-lift="1">${icon("mdi:arrow-up-bold")}</button>` +
          `<button class="hold small" data-lift="-1">${icon("mdi:arrow-down-bold")}</button></div>` +
          `</div>` +
          `<div class="speed">` +
          `<button data-speed="slow">${t("slow")}</button>` +
          `<button data-speed="normal">${t("normal")}</button>` +
          `<button data-speed="fast">${t("fast")}</button>` +
          `<span class="sep"></span><button class="hold-t">${icon("mdi:hand-back-right")}<span>${t("hold")}</span></button>` +
          `</div>` +
          `<div class="actions">` +
          `<button data-press="drive_off_charger">${icon("mdi:arrow-up-box")}${t("drive_off")}</button>` +
          `<button data-press="drive_on_charger">${icon("mdi:battery-charging")}${t("to_charger")}</button>` +
          `<button data-press="refresh_camera">${icon("mdi:camera-retake")}${t("snapshot")}</button>` +
          `</div>` +
          `</ha-card>`;
        this._root = root;
        this._card = root.querySelector("ha-card");
        this._cam = root.querySelector(".cam");
        this._still = root.querySelector(".cam .still");
        this._status = root.querySelector(".status");

        this._wireHoldButtons(root);
        root.querySelector("button.stop").addEventListener("click", () => this._stopNow());
        root.querySelectorAll(".speed button[data-speed]").forEach((btn) => {
          btn.addEventListener("click", () => this._setSpeed(btn.dataset.speed));
        });
        root.querySelector(".speed .hold-t").addEventListener("click", () => {
          const on = !this._holding();
          this._manualHold = on; // the user's own hold is not released automatically
          this._setHold(on);
        });
        root.querySelectorAll(".actions button, .charger button").forEach((btn) => {
          btn.addEventListener("click", () => this._pressButton(btn.dataset.press));
        });
        root.querySelector(".cam .play").addEventListener("click", () => this._goLive());
        root.querySelector(".cam .close").addEventListener("click", () => this._stopLive());
        root.querySelector(".cam .full").addEventListener("click", () => this._openFull());
        root.querySelector(".cam .mute").addEventListener("click", () => this._toggleTileMute());
        // A still that fails to load (no cached frame yet, robot offline) is simply hidden:
        // the placeholder stays instead of the browser's broken-image icon.
        this._still.addEventListener("load", () => this._setStill(true));
        this._still.addEventListener("error", () => this._setStill(false));
        if (!this._activityWired) {
          this._activityWired = true; // the shadow root survives rebuilds (setConfig)
          root.addEventListener("pointerdown", () => this._noteActivity(), true);
        }
        this._built = true;
        this._stillToken = undefined;
      }

      _wireHoldButtons(root) {
        root.querySelectorAll("button.hold").forEach((btn) => {
          btn.addEventListener("pointerdown", (ev) => {
            ev.preventDefault();
            if (btn.setPointerCapture) {
              try {
                btn.setPointerCapture(ev.pointerId);
              } catch (_) {
                /* synthetic pointer */
              }
            }
            this._startHold(btn);
          });
          ["pointerup", "pointercancel", "lostpointercapture"].forEach((name) => {
            btn.addEventListener(name, () => {
              if (this._holdBtn === btn) this._stopHold();
            });
          });
          btn.addEventListener("contextmenu", (ev) => ev.preventDefault());
        });
      }

      _setStill(on) {
        if (!this._still) return;
        this._still.classList.toggle("on", on);
        this._cam.classList.toggle("still-on", on);
      }

      // The last cached frame (never wakes the camera); refreshed when the camera token rotates.
      _refreshStill() {
        const cam = this._camState();
        if (!this._still) return;
        if (!cam || this._offline()) {
          this._still.removeAttribute("src");
          this._stillToken = undefined;
          this._setStill(false);
          return;
        }
        const token = cam.attributes.access_token;
        if (!token || token === this._stillToken) return;
        this._stillToken = token;
        this._still.src = `/api/camera_proxy/${this._config.camera}?token=${token}&t=${Date.now()}`;
      }

      _placeholder(title, hint, retry) {
        const ph = this._cam && this._cam.querySelector(".ph");
        if (!ph) return;
        ph.querySelector(".t").textContent = title || "";
        ph.querySelector(".h").textContent = hint || "";
        const old = ph.querySelector("button");
        if (old) old.remove();
        if (retry) {
          const b = document.createElement("button");
          b.textContent = this._t("retry");
          b.addEventListener("click", () => this._goLive());
          ph.appendChild(b);
        }
      }

      _update() {
        if (!this._built || !this._hass) return;
        const offline = this._offline();
        this._card.classList.toggle("offline", offline);
        this._cam.classList.toggle("can-play", !offline);
        if (offline) {
          this._stopLive();
          this._placeholder(this._t("unavailable"), this._t("unavailable_hint"));
        } else if (!this._live && !this._liveError) {
          this._placeholder(this._t("no_preview"), this._t("no_preview_hint"));
        }
        this._refreshStill();

        const parts = [];
        const bat = this._sibling("sensor", "battery");
        parts.push(`${this._t("battery")} <b>${noValue(bat) ? "—" : Math.round(Number(bat.state)) + " %"}</b>`);
        const act = this._sibling("sensor", "activity");
        if (!noValue(act)) parts.push(`${this._t("doing")} <b>${this._escape(act.state)}</b>`);
        const charger = this._sibling("binary_sensor", "on_charger");
        if (charger && charger.state === "off") parts.push(this._t("off_charger"));
        this._root.querySelector(".charger").classList.toggle("on", !offline && !!charger && charger.state === "on");
        this._status.innerHTML = parts.join(" · ");
        this._root.querySelectorAll(".speed button[data-speed]").forEach((b) => {
          b.classList.toggle("on", b.dataset.speed === this._speed);
        });
        const held = this._holding();
        const ht = this._root.querySelector(".speed .hold-t");
        ht.classList.toggle("on", held);
        ht.querySelector("span").textContent = this._t(held ? "holding" : "hold");
        if (this._fsOpen) this._updateFs();
      }

      _escape(text) {
        const d = document.createElement("div");
        d.textContent = String(text);
        return d.innerHTML;
      }

      /* ---------------- driving ---------------- */

      _setSpeed(speed) {
        this._speed = speed;
        this._update();
      }

      _vector(base) {
        const f = this._config.speed || 120;
        const v = Math.round(f * (SPEEDS[this._speed] || 1));
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
        if (this._offline()) return;
        // "forward" on the charger = drive off it (Vector leaves the station himself). Once per
        // DRIVE_OFF_EVERY_MS: every tap used to send it again and the robot answered each one with
        // BEHAVIOR_WONT_ACTIVATE_STATE (a stack of error toasts) while it was still busy.
        if (btn.dataset.drive === "fwd" && this._onCharger()) {
          const now = Date.now();
          if (now - (this._driveOffAt || 0) > DRIVE_OFF_EVERY_MS) {
            this._driveOffAt = now;
            this._pressButton("drive_off_charger");
          }
          this._notify(this._t("driving_off"));
          return;
        }
        this._autoHold(); // steering takes behavior control
        let data;
        if (btn.dataset.drive) data = this._vector(btn.dataset.drive);
        else if (btn.dataset.head) data = { head: Number(btn.dataset.head) * 1.2 };
        else if (btn.dataset.lift) data = { lift: Number(btn.dataset.lift) * 1.5 };
        if (!data) return;
        btn.classList.add("active");
        this._holdBtn = btn;
        this._call("move", data);
        this._holdTimer = setInterval(() => this._call("move", data), REPEAT_MS);
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

      _stopNow() {
        this._stopHold(true);
        this._call("stop", {});
      }

      // Every way a hold can end without a pointerup lands here: the robot must stop.
      _releaseControls() {
        this._stopHold();
      }

      _callRaw(domain, service, data) {
        if (!this._hass) return;
        const p = this._hass.callService(domain, service, data);
        if (p && p.catch) {
          p.catch((err) => console.warn(`${domain}.${service}`, err && err.message));
        }
      }

      _call(service, data) {
        const payload = Object.assign({}, data);
        const dev = this._deviceId();
        if (dev) payload.device_id = dev;
        this._callRaw("vector", service, payload);
      }

      _pressButton(key) {
        const st = this._sibling("button", key);
        if (st) this._callRaw("button", "press", { entity_id: st.entity_id });
      }

      /* ---------------- live view ---------------- */

      // The player: Home Assistant's ha-camera-stream (WebRTC from go2rtc) when the camera has a
      // stream, otherwise MJPEG through the camera proxy. fit: "cover" fills the area.
      async _createPlayer(fit) {
        const cam = this._camState();
        if (!cam) return null;
        if (this._hasStream()) {
          try {
            const helpers = window.loadCardHelpers ? await window.loadCardHelpers() : null;
            if (!customElements.get("ha-camera-stream") && helpers) {
              // the picture card imports ha-camera-stream: creating one loads the player module
              try {
                helpers.createCardElement({ type: "picture-entity", entity: this._config.camera, camera_view: "live" });
              } catch (_) {
                /* ignore */
              }
            }
            await Promise.race([
              customElements.whenDefined("ha-camera-stream"),
              new Promise((r) => setTimeout(r, 4000)),
            ]);
          } catch (_) {
            /* fall back to MJPEG */
          }
          if (customElements.get("ha-camera-stream")) {
            const live = document.createElement("ha-camera-stream");
            live.hass = this._hass;
            live.stateObj = this._camState();
            live.muted = true; // autoplay only works muted; 🔊 unmutes with a tap (iOS)
            live.controls = false;
            live.fitMode = fit;
            live.setAttribute("fit-mode", fit);
            return live;
          }
        }
        const img = document.createElement("img");
        img.alt = "";
        img.src = `/api/camera_proxy_stream/${this._config.camera}?token=${cam.attributes.access_token}&t=${Date.now()}`;
        img.addEventListener("error", () => this._onLiveError(img));
        return img;
      }

      _onLiveError(el) {
        // MJPEG broken (the robot camera sends no frames; the add-on closes the stream after 30 s)
        if (el === this._live) {
          this._stopLive();
          this._liveError = true;
          this._placeholder(this._t("no_camera"), "", true);
        } else if (el === this._fsLive) {
          this._fsStopLive();
          this._fsToast(this._t("no_camera"));
        }
      }

      async _goLive() {
        if (this._live || this._starting || this._offline() || !this._cam) return;
        this._starting = true;
        this._liveError = false;
        this._placeholder(this._t("connecting"), "");
        const live = await this._createPlayer("cover");
        this._starting = false;
        if (!live || !this._cam || this._fsOpen || this._offline()) return;
        live.classList.add("live");
        this._cam.insertBefore(live, this._cam.querySelector(".ph")); // under the buttons
        this._live = live;
        this._cam.classList.add("live-on");
        this._tileMuted = true;
        this._setTileMuteIcon();
        clearInterval(this._tileLoadTimer);
        this._tileLoadTimer = this._watchLoading(live, this._cam.querySelector(".cam-load"), () => {
          this._stopLive();
          this._notify(this._t("live_failed"));
        });
        this._startLiveGuard();
      }

      _stopLive() {
        clearInterval(this._tileLoadTimer);
        const load = this._cam && this._cam.querySelector(".cam-load");
        if (load) load.classList.remove("show");
        if (this._live) {
          this._live.remove(); // HA closes the stream → go2rtc stops → the camera stops
          this._live = null;
        }
        if (this._cam) this._cam.classList.remove("live-on");
        if (!this._fsLive) this._stopLiveGuard();
        if (this._built && !this._offline() && !this._liveError) {
          this._placeholder(this._t("no_preview"), this._t("no_preview_hint"));
        }
      }

      _noteActivity() {
        this._lastActivity = Date.now();
      }

      _startLiveGuard() {
        this._noteActivity();
        if (this._liveGuardTimer) return;
        this._liveGuardTimer = setInterval(() => {
          if ((this._live || this._fsLive) && Date.now() - (this._lastActivity || 0) > LIVE_IDLE_MS) {
            this._pauseLive(true);
          }
        }, LIVE_GUARD_TICK_MS);
      }

      _stopLiveGuard() {
        clearInterval(this._liveGuardTimer);
        this._liveGuardTimer = null;
      }

      _pauseLive(notify) {
        const wasFs = !!this._fsLive;
        if (this._live) this._stopLive();
        if (this._fsLive) this._fsStopLive();
        this._stopLiveGuard();
        if (wasFs && notify) this._fsToast(this._t("live_paused"));
      }

      /* ---------------- full screen ---------------- */

      _fs(id) {
        return this._fsRoot ? this._fsRoot.getElementById(id) : null;
      }

      _ensureFs() {
        if (this._fsHost) return;
        const t = this._t.bind(this);
        const host = document.createElement("div");
        host.className = "vector-fs-host";
        host.style.cssText = "position:fixed;inset:0;z-index:2147483000;display:none;";
        const root = host.attachShadow({ mode: "open" });
        root.innerHTML =
          `<style>${FS_STYLE}</style>` +
          `<div class="fs" id="fs">` +
          `<div class="fs-cam" id="fs-cam"><div class="fs-still" id="fs-still"></div></div>` +
          `<div class="fs-grad"></div>` +
          `<div class="fs-rotate">${icon("mdi:phone-rotate-landscape")}<div>${t("rotate")}</div></div>` +
          `<div class="fs-ui">` +
          `<div class="fs-topl">` +
          `<button class="fs-back" id="fs-back" title="${t("exit_full")}">${icon("mdi:chevron-left")}</button>` +
          `<span class="fs-clock" id="fs-clock"></span><span class="fs-batt" id="fs-batt"></span>` +
          `</div>` +
          `<button class="fs-play" id="fs-play" title="${t("live")}">` +
          `<span class="fs-play-ic">${icon("mdi:play")}</span><span class="fs-play-lbl">${t("start_live")}</span></button>` +
          `<div class="fs-load" id="fs-load"><span class="spin"></span><span>${t("loading")}</span></div>` +
          `<div class="fs-off">${icon("mdi:robot-off-outline")}<div>${t("unavailable")}</div>` +
          `<div class="h">${t("unavailable_hint")}</div></div>` +
          `<div class="fs-pad">` +
          `<span></span><button class="fs-btn hold" data-drive="fwd">${icon("mdi:chevron-up")}</button><span></span>` +
          `<button class="fs-btn hold" data-drive="left">${icon("mdi:rotate-left")}</button>` +
          `<button class="fs-stop" id="fs-stop">STOP</button>` +
          `<button class="fs-btn hold" data-drive="right">${icon("mdi:rotate-right")}</button>` +
          `<span></span><button class="fs-btn hold" data-drive="back">${icon("mdi:chevron-down")}</button><span></span>` +
          `</div>` +
          `<div class="fs-rail">` +
          `<button class="fs-ic fs-mute muted" id="fs-mute" title="${t("listen_on")}">${icon("mdi:volume-off")}</button>` +
          `<div class="fs-group"><span class="fs-lbl">${t("head")}</span><div class="fs-pill">` +
          `<button class="hold" data-head="1">${icon("mdi:arrow-up-bold")}</button>` +
          `<button class="hold" data-head="-1">${icon("mdi:arrow-down-bold")}</button></div></div>` +
          `<div class="fs-group"><span class="fs-lbl">${t("lift")}</span><div class="fs-pill">` +
          `<button class="hold" data-lift="1">${icon("mdi:arrow-up-bold")}</button>` +
          `<button class="hold" data-lift="-1">${icon("mdi:arrow-down-bold")}</button></div></div>` +
          `</div>` +
          `<div class="fs-bottom">` +
          `<button data-speed="slow">${t("slow")}</button>` +
          `<button data-speed="normal">${t("normal")}</button>` +
          `<button data-speed="fast">${t("fast")}</button>` +
          `<span class="sep"></span>` +
          `<button data-press="drive_off_charger" title="${t("drive_off")}">${icon("mdi:arrow-up-box")}</button>` +
          `<button data-press="drive_on_charger" title="${t("to_charger")}">${icon("mdi:battery-charging")}</button>` +
          `</div>` +
          `<div class="fs-toast" id="fs-toast"></div>` +
          `</div></div>`;
        this._fsHost = host;
        this._fsRoot = root;
        root.addEventListener("pointerdown", () => this._noteActivity(), true);
        this._wireHoldButtons(root);
        this._fs("fs-back").addEventListener("click", () => this._closeFull());
        this._fs("fs-stop").addEventListener("click", () => this._stopNow());
        this._fs("fs-play").addEventListener("click", () => this._fsPlay());
        this._fs("fs-mute").addEventListener("click", () => this._toggleMute());
        root.querySelectorAll(".fs-bottom button[data-speed]").forEach((b) => {
          b.addEventListener("click", () => this._setSpeed(b.dataset.speed));
        });
        root.querySelectorAll(".fs-bottom button[data-press]").forEach((b) => {
          b.addEventListener("click", () => this._pressButton(b.dataset.press));
        });
        // no page scrolling or rubber-banding under the view
        this._fs("fs").addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
      }

      async _openFull() {
        if (this._fsOpen) return;
        this._ensureFs();
        const host = this._fsHost;
        this._stopLive(); // one viewer at a time
        this._fsOpen = true;
        // Inside <home-assistant>, not <body>: Home Assistant's player (ha-camera-stream) takes its
        // config and connection from Lit context, which only reaches that tree. In <body> it
        // rendered nothing — the full screen stayed black although the robot was streaming.
        const haRoot = document.querySelector("home-assistant");
        (haRoot && haRoot.shadowRoot ? haRoot.shadowRoot : document.body).appendChild(host);
        host.style.display = "block";
        this._autoHold(); // the control view steers: take behavior control while it is open
        // real full screen where the browser allows it (iPad, Android), requested within the tap
        let fsReq = null;
        try {
          if (host.requestFullscreen) fsReq = host.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
        } catch (_) {
          /* iPhone: no Fullscreen API, the overlay still covers the screen */
        }
        this._fsMuted = true;
        this._applyMuteIcon();
        this._showPlay(true);
        this._showFsStill();
        this._onOrient = () => this._updateFsOrientation();
        window.addEventListener("resize", this._onOrient);
        window.addEventListener("orientationchange", this._onOrient);
        this._updateFsOrientation();
        this._tickClock();
        clearInterval(this._clockTimer);
        this._clockTimer = setInterval(() => this._tickClock(), 1000);
        clearInterval(this._fitTimer);
        this._fitTimer = setInterval(() => this._applyMute(), 1000);
        this._updateFs();
        if (fsReq) {
          await fsReq;
          try {
            if (screen.orientation && screen.orientation.lock) screen.orientation.lock("landscape").catch(() => {});
          } catch (_) {
            /* ignore */
          }
        }
      }

      _closeFull() {
        // Closing mid-drive (thumb on the pad, other hand on "back"): removing the view takes the
        // pointerup with it, so the hold is ended explicitly — the robot must not keep driving.
        this._releaseControls();
        const wasOpen = this._fsOpen;
        this._fsOpen = false;
        if (wasOpen) this._releaseAutoHold(); // closing the view gives control back to Vector
        clearInterval(this._clockTimer);
        this._clockTimer = null;
        clearInterval(this._fitTimer);
        this._fitTimer = null;
        if (this._onOrient) {
          window.removeEventListener("resize", this._onOrient);
          window.removeEventListener("orientationchange", this._onOrient);
          this._onOrient = null;
        }
        try {
          if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock();
        } catch (_) {
          /* ignore */
        }
        try {
          if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        } catch (_) {
          /* ignore */
        }
        if (this._fsLive) {
          this._fsLive.remove();
          this._fsLive = null;
        }
        if (this._fsHost) {
          this._fsHost.style.display = "none";
          this._fsHost.remove();
        }
        if (!this._live) this._stopLiveGuard();
      }

      _updateFs() {
        const fs = this._fs("fs");
        if (!fs) return;
        const offline = this._offline();
        fs.classList.toggle("offline", offline);
        if (offline && this._fsLive) this._fsStopLive();
        if (offline) this._showPlay(false);
        else if (!this._fsLive && !this._fsStarting) this._showPlay(true);
        const bat = this._sibling("sensor", "battery");
        const b = this._fs("fs-batt");
        if (b) {
          b.innerHTML = noValue(bat)
            ? ""
            : `${icon(this._onCharger() ? "mdi:battery-charging" : "mdi:battery")}${Math.round(Number(bat.state))} %`;
        }
        this._fsRoot.querySelectorAll(".fs-bottom button[data-speed]").forEach((btn) => {
          btn.classList.toggle("on", btn.dataset.speed === this._speed);
        });
        const mute = this._fs("fs-mute");
        if (mute) {
          mute.classList.toggle("disabled", !this._hasStream());
          mute.title = this._hasStream() ? (this._fsMuted ? this._t("listen_on") : this._t("listen_off")) : this._t("no_audio");
        }
      }

      _updateFsOrientation() {
        const fs = this._fs("fs");
        if (!fs) return;
        fs.classList.toggle("portrait", window.innerHeight > window.innerWidth);
        // Which side is the island on? iOS safe areas are symmetric, the island is on one side:
        // window.orientation 90 → top of the phone (island) on the left, -90 → on the right.
        const wo = typeof window.orientation === "number" ? window.orientation : null;
        const ang = screen.orientation && typeof screen.orientation.angle === "number" ? screen.orientation.angle : null;
        let side = "";
        if (wo === 90 || (wo === null && ang === 90)) side = "left";
        else if (wo === -90 || (wo === null && ang === 270)) side = "right";
        fs.classList.toggle("island-left", side === "left");
        fs.classList.toggle("island-right", side === "right");
      }

      _tickClock() {
        const el = this._fs("fs-clock");
        if (!el) return;
        const d = new Date();
        const p = (n) => String(n).padStart(2, "0");
        el.textContent = `${p(d.getHours())}:${p(d.getMinutes())}`;
      }

      _showFsStill() {
        const el = this._fs("fs-still");
        const cam = this._camState();
        if (!el) return;
        const token = cam && !this._offline() ? cam.attributes.access_token : "";
        el.style.backgroundImage = token
          ? `url("/api/camera_proxy/${this._config.camera}?token=${token}&t=${Date.now()}")`
          : "none";
      }

      _showPlay(on) {
        const play = this._fs("fs-play");
        if (play) play.style.display = on ? "flex" : "none";
      }

      async _fsPlay() {
        if (this._fsLive || this._fsStarting || this._offline()) return;
        this._fsStarting = true;
        this._showPlay(false);
        const fsLoad = this._fs("fs-load");
        if (fsLoad) fsLoad.classList.add("show");
        const live = await this._createPlayer("cover");
        this._fsStarting = false;
        const host = this._fs("fs-cam");
        if (!live || !host || !this._fsOpen) {
          if (fsLoad) fsLoad.classList.remove("show");
          if (this._fsOpen) this._showPlay(true);
          return;
        }
        live.classList.add("fs-live");
        host.appendChild(live);
        this._fsLive = live;
        this._fsMuted = true;
        this._applyMuteIcon();
        this._applyMute();
        if (this._hasStream()) this._fsToast(this._t("tap_sound"));
        clearInterval(this._fsLoadTimer);
        this._fsLoadTimer = this._watchLoading(live, fsLoad, () => {
          this._fsStopLive();
          this._fsToast(this._t("live_failed"));
        });
        this._startLiveGuard();
      }

      _fsStopLive() {
        clearInterval(this._fsLoadTimer);
        const load = this._fs("fs-load");
        if (load) load.classList.remove("show");
        if (this._fsLive) {
          this._fsLive.remove(); // HA closes the stream → go2rtc stops → the camera stops
          this._fsLive = null;
        }
        this._fsMuted = true;
        this._applyMuteIcon();
        this._showFsStill();
        if (this._fsOpen && !this._offline()) this._showPlay(true);
        if (!this._live) this._stopLiveGuard();
      }

      // Spinner until the player has a frame (video.readyState >= 2); MJPEG <img> needs none.
      _watchLoading(live, loader, onFail) {
        if (!loader) return undefined;
        loader.classList.add("show");
        const startedAt = Date.now();
        const timer = setInterval(() => {
          const playing = this._findVideos(live).some((v) => v.readyState >= 2 && v.videoWidth > 0);
          if (playing || live.tagName === "IMG" || !live.isConnected) {
            loader.classList.remove("show");
            clearInterval(timer);
          } else if (Date.now() - startedAt > LIVE_LOAD_MAX_MS) {
            loader.classList.remove("show");
            clearInterval(timer);
            if (onFail) onFail();
          }
        }, 400);
        return timer;
      }

      // Speaker on the tile (portrait has no full screen with 🔊). A tap = a gesture (iOS sound).
      _toggleTileMute() {
        if (!this._live) return;
        if (!this._hasStream()) {
          this._notify(this._t("no_audio"));
          return;
        }
        this._tileMuted = this._tileMuted === false;
        for (const v of this._findVideos(this._live)) {
          v.muted = this._tileMuted;
          if (!this._tileMuted) {
            v.volume = 1;
            const p = v.play && v.play();
            if (p && p.catch) p.catch(() => {});
          }
        }
        if ("muted" in this._live) this._live.muted = this._tileMuted;
        this._setTileMuteIcon();
      }

      _setTileMuteIcon() {
        const b = this._cam && this._cam.querySelector(".mute");
        if (!b) return;
        b.innerHTML = icon(this._tileMuted === false ? "mdi:volume-high" : "mdi:volume-off");
        b.classList.toggle("on", this._tileMuted === false);
      }

      // A message where the user looks: the full screen or a bubble on the tile's camera.
      _notify(msg) {
        if (this._fsOpen) {
          this._fsToast(msg);
          return;
        }
        const el = this._cam && this._cam.querySelector(".cam-toast");
        if (!el) return;
        el.textContent = msg;
        el.classList.add("show");
        clearTimeout(this._tileToastTimer);
        this._tileToastTimer = setTimeout(() => el.classList.remove("show"), 2500);
      }

      _findVideos(el, out = []) {
        if (!el) return out;
        if (el.tagName === "VIDEO") {
          out.push(el);
          return out;
        }
        if (el.shadowRoot) for (const c of el.shadowRoot.children) this._findVideos(c, out);
        if (el.children) for (const c of el.children) this._findVideos(c, out);
        return out;
      }

      // Every second: fill the screen with the video (the player creates it late and may recreate
      // it on reconnect) and keep it muted until the user taps 🔊.
      _applyMute() {
        if (!this._fsLive) return;
        for (const v of this._findVideos(this._fsLive)) {
          v.style.objectFit = "cover";
          v.style.width = "100%";
          v.style.height = "100%";
          v.style.maxHeight = "none"; // HA players have max-height: calc(100vh - 97px)
          const player = v.getRootNode && v.getRootNode().host;
          if (player && player !== this._fsLive && player.style) {
            player.style.display = "block";
            player.style.width = "100%";
            player.style.height = "100%";
          }
          if (this._fsMuted && !v.muted) v.muted = true;
        }
      }

      _applyMuteIcon() {
        const b = this._fs("fs-mute");
        if (!b) return;
        b.innerHTML = icon(this._fsMuted ? "mdi:volume-off" : "mdi:volume-high");
        b.classList.toggle("muted", this._fsMuted);
        b.classList.toggle("listening", !this._fsMuted);
        b.title = this._fsMuted ? this._t("listen_on") : this._t("listen_off");
      }

      // Called from a tap (a user gesture): the only way iOS lets a video play sound.
      _toggleMute() {
        if (!this._hasStream()) {
          this._fsToast(this._t("no_audio"));
          return;
        }
        if (!this._fsLive) {
          this._fsToast(this._t("no_preview_hint"));
          return;
        }
        this._fsMuted = !this._fsMuted;
        for (const v of this._findVideos(this._fsLive)) {
          v.muted = this._fsMuted;
          if (!this._fsMuted) {
            v.volume = 1;
            const p = v.play && v.play();
            if (p && p.catch) p.catch(() => {});
          }
        }
        if ("muted" in this._fsLive) this._fsLive.muted = this._fsMuted;
        this._applyMuteIcon();
      }

      _fsToast(msg) {
        const el = this._fs("fs-toast");
        if (!el) return;
        el.textContent = msg;
        el.classList.add("show");
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
      }
    };
  }

  // Extra modules (add_extra_js_url) load before the scoped CustomElementRegistry polyfill,
  // so the card is only registered once <home-assistant> exists.
  function registerCard() {
    const registry = window.customElements;
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
    setTimeout(() => waitForFrontend(attempt + 1), 50);
  })(0);
})();
