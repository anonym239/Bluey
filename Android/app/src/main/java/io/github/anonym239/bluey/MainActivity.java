package io.github.anonym239.bluey;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.text.InputType;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;

/** Sein Gesicht. Doppelt tippen: aufwecken / zurück in den Folgemodus. Gedrückt halten: fragen, loslassen: Antwort. */
public final class MainActivity extends Activity {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private PhoneCredentials settings;
    private DesktopLink link;
    private LiveVoice voice;
    private SessionStore store;
    private NotesSync notes;
    private SpeechOutput speech;
    private WifiManager.MulticastLock multicast;

    private FrameLayout root;
    private FaceView face;
    private ModeIndicator indicator;
    private CaptionBubble bubble;
    private ReportCard report;
    private SoundPanel sound;
    private View pairing;
    private BlueyAppView app;
    private MousePointer pointer;
    private boolean showPairing = true, holdingToAsk, started;
    private final Runnable holdStart = this::beginHold;
    private boolean wasConnected;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Fonts.load(this);
        settings = new PhoneCredentials(this);
        store = new SessionStore(getFilesDir());
        speech = new SpeechOutput(this);
        ChunkRecorder recorder = new ChunkRecorder(getFilesDir());
        voice = new LiveVoice(recorder, settings, speech);
        link = new DesktopLink(this, new DesktopLink.Listener() {
            @Override public void changed() { linkChanged(); }
            @Override public void face(double gx, double gy, Mood mood, double talk) {
                face.animator.receive(gx, gy, mood, talk, FaceView.now());
            }
            @Override public void command(String command, JSONObject packet) {
                switch (command) {
                    case "wake": if (hasMic()) voice.wake(); else askMic(); break;
                    case "sleep": voice.sleep(); break;
                    case "voiceEvent": voice.handleLocal(Json.parse(Json.str(packet, "text"))); break;
                    case "pointer": pointer.handle(Json.parse(Json.str(packet, "text"))); break;
                    default: break;
                }
            }
        });
        notes = new NotesSync(getFilesDir(), store, link, settings);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        buildViews();
        wireVoice();
        WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
        if (wifi != null) {
            multicast = wifi.createMulticastLock("Bluey-Suche");
            multicast.setReferenceCounted(false);
        }
    }

    // Ansicht

    private void buildViews() {
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        face = new FaceView(this);
        face.animator.localTalk = voice::level;
        root.addView(face, new FrameLayout.LayoutParams(-1, -1));
        indicator = new ModeIndicator(this);
        root.addView(indicator, new FrameLayout.LayoutParams(-1, -1));
        bubble = new CaptionBubble(this);
        root.addView(bubble, new FrameLayout.LayoutParams(-1, -1));
        report = new ReportCard(this);
        FrameLayout.LayoutParams reportParams = new FrameLayout.LayoutParams(Ui.dp(this, 380), -2, Gravity.TOP | Gravity.END);
        reportParams.setMargins(0, Ui.dp(this, 62), Ui.dp(this, 20), 0);
        root.addView(report, reportParams);
        report.setVisibility(View.GONE);

        // Oben rechts: Blueys App (Sitzungen, Transkripte, Einstellungen) und der leise Lautsprecher-Knopf.
        Icons.Button appButton = new Icons.Button(this, Icons.Kind.GRID);
        appButton.setContentDescription("Bluey öffnen");
        appButton.setOnClickListener(v -> showApp(true));
        FrameLayout.LayoutParams appParams = new FrameLayout.LayoutParams(Ui.dp(this, 44), Ui.dp(this, 44), Gravity.TOP | Gravity.END);
        appParams.setMargins(0, Ui.dp(this, 10), Ui.dp(this, 62), 0);
        root.addView(appButton, appParams);

        sound = new SoundPanel(this, new SoundPanel.Host() {
            @Override public double volume() { return settings.volume(); }
            @Override public void setVolume(double v) { voice.setVolume(v); }
            @Override public LiveVoice.State state() { return voice.state; }
            @Override public void sayHi() { if (!hasMic()) askMic(); else voice.sayHi(); }
            @Override public DesktopLink link() { return link; }
            @Override public boolean phoneMode() { return settings.phoneMode(); }
            @Override public void manual() { manualAddress(); }
            @Override public void settings() { voiceSettings(); }
        });
        FrameLayout.LayoutParams soundParams = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.END);
        soundParams.setMargins(0, Ui.dp(this, 10), Ui.dp(this, 14), 0);
        root.addView(sound, soundParams);

        pairing = buildPairing();
        root.addView(pairing, new FrameLayout.LayoutParams(-1, -1));

        app = new BlueyAppView(this, store, new BlueyAppView.Host() {
            @Override public LiveVoice.State state() { return voice.state; }
            @Override public void toggleSession() {
                boolean starting = voice.state == LiveVoice.State.ASLEEP;
                if (starting && !hasMic()) { askMic(); return; }
                voice.toggle();
                if (starting) showApp(false);  // zurück zum Gesicht beim Start
            }
            @Override public boolean canStart() { return link.connected || settings.phoneMode(); }
            @Override public DesktopLink link() { return link; }
            @Override public double volume() { return settings.volume(); }
            @Override public void setVolume(double v) { voice.setVolume(v); }
            @Override public void close() { showApp(false); }
            @Override public void settings() { voiceSettings(); }
            @Override public boolean phoneMode() { return settings.phoneMode(); }
        });
        app.setVisibility(View.GONE);
        root.addView(app, new FrameLayout.LayoutParams(-1, -1));

        // Die PC-Maus auf dem Handy (unten am PC-Bildschirm hinausschieben). Seine Augen folgen ihr.
        pointer = new MousePointer(this, root, (x, y, visible) -> {
            if (visible && app.getVisibility() != View.VISIBLE) {
                double[] gaze = face.gazeFor(x, y);
                face.animator.touchX = gaze[0];
                face.animator.touchY = gaze[1];
            } else {
                face.animator.touchX = face.animator.touchY = null;
            }
        });
        root.addView(pointer, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        hideSystemBars();

        GestureDetector gestures = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onDown(MotionEvent e) { return true; }
            @Override public boolean onDoubleTap(MotionEvent e) {
                ui.removeCallbacks(holdStart);
                if (voice.state == LiveVoice.State.ASLEEP && !hasMic()) { askMic(); return true; }
                if (voice.state == LiveVoice.State.ASLEEP && !canTalk()) { explainNoBrain(); return true; }
                voice.toggle();
                return true;
            }
        });
        gestures.setIsLongpressEnabled(false);
        face.setOnTouchListener((v, event) -> {
            gestures.onTouchEvent(event);
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN) {
                if (sound.isOpen()) sound.close();
                ui.postDelayed(holdStart, 300);  // ein kurzes Tippen ist kein Halten
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                ui.removeCallbacks(holdStart);
                if (holdingToAsk) {
                    holdingToAsk = false;
                    buzz(12);
                    voice.endAsk();
                } else if (action == MotionEvent.ACTION_UP) {
                    v.performClick();
                }
            }
            return true;
        });
        ui.post(this::tick);
    }

    /** Langsamer Takt für Dinge, die sich mit der Zeit ändern (Etikett, Verbindung). */
    private void tick() {
        indicator.suffix = settings.phoneMode() && voice.state != LiveVoice.State.ASLEEP ? "ohne PC" : null;
        ui.postDelayed(this::tick, 1000);
    }

    private void beginHold() {
        if (!hasMic()) { askMic(); return; }
        if (voice.state == LiveVoice.State.ASLEEP && !canTalk()) { explainNoBrain(); return; }
        holdingToAsk = true;
        buzz(20);
        bubble.show(null, false);
        voice.beginAsk();
    }

    private boolean canTalk() { return link.connected || settings.phoneMode(); }

    private void explainNoBrain() {
        bubble.show("Verbinde mich mit deinem PC (oder stell in den Einstellungen „Nur Handy“ ein).", true);
    }

    private void buzz(int ms) {
        Vibrator vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        if (vibrator == null || !vibrator.hasVibrator()) return;
        try { vibrator.vibrate(VibrationEffect.createOneShot(ms, 60)); } catch (Exception ignored) {}
    }

    private View buildPairing() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        row.setBackgroundColor(Color.BLACK);
        row.setPadding(Ui.dp(this, 48), Ui.dp(this, 16), Ui.dp(this, 48), Ui.dp(this, 16));
        row.setClickable(true);
        Ui.SleepyBlob blob = new Ui.SleepyBlob(this);
        LinearLayout.LayoutParams blobParams = new LinearLayout.LayoutParams(Ui.dp(this, 220), Ui.dp(this, 190));
        blobParams.rightMargin = Ui.dp(this, 48);
        row.addView(blob, blobParams);

        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.addView(Ui.text(this, "Weck mich von deinem PC auf", Fonts.display, 28, 0xFFF4F1FA));
        TextView body = Ui.text(this, "Starte Bluey auf deinem Windows-PC. Bleibt beide im selben WLAN, dann finde ich ihn. "
            + "Die KI läuft dort mit Ollama auf deiner Grafikkarte.", Fonts.sans, 15, Palette.INK_SOFT);
        body.setMaxWidth(Ui.dp(this, 400));
        body.setPadding(0, Ui.dp(this, 10), 0, Ui.dp(this, 10));
        column.addView(body);
        LinearLayout looking = new LinearLayout(this);
        looking.setGravity(Gravity.CENTER_VERTICAL);
        looking.addView(new Ui.Spinner(this), new LinearLayout.LayoutParams(Ui.dp(this, 18), Ui.dp(this, 18)));
        TextView lookingText = Ui.text(this, "  Suche deinen PC", Fonts.mono, 13, Palette.INK_SOFT);
        looking.addView(lookingText);
        column.addView(looking);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        buttons.setPadding(0, Ui.dp(this, 16), 0, 0);
        LinearLayout play = Ui.button(this, null, "Ohne PC spielen", Fonts.sansBold, 15, Ui.round(Palette.PANEL, 14, this));
        play.setOnClickListener(v -> { showPairing = false; linkChanged(); });
        buttons.addView(play);
        View gap = new View(this);
        buttons.addView(gap, new LinearLayout.LayoutParams(Ui.dp(this, 10), 1));
        LinearLayout ip = Ui.button(this, null, "IP eingeben", Fonts.sansBold, 15, Ui.round(Palette.PANEL, 14, this));
        ip.setOnClickListener(v -> manualAddress());
        buttons.addView(ip);
        View gap2 = new View(this);
        buttons.addView(gap2, new LinearLayout.LayoutParams(Ui.dp(this, 10), 1));
        LinearLayout phone = Ui.button(this, null, "Nur Handy", Fonts.sansBold, 15, Ui.berry(14, this));
        phone.setOnClickListener(v -> voiceSettings());
        buttons.addView(phone);
        column.addView(buttons);
        row.addView(column);
        return row;
    }

    private void showApp(boolean show) {
        app.setVisibility(show ? View.VISIBLE : View.GONE);
        if (show) app.refresh();
    }

    @Override public void onBackPressed() {
        if (app.getVisibility() == View.VISIBLE) {
            if (!app.back()) showApp(false);
            return;
        }
        if (sound.isOpen()) { sound.close(); return; }
        super.onBackPressed();
    }

    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemBars();
    }

    private void linkChanged() {
        boolean connected = link.connected;
        pairing.setVisibility(showPairing && !connected && !settings.phoneMode() ? View.VISIBLE : View.GONE);
        if (connected && !wasConnected) {
            showPairing = false;
            pairing.setVisibility(View.GONE);
            notes.retryPending();
            store.resyncRecent();
            voice.desktopReconnected();
        }
        if (!connected && pointer != null && pointer.isVisible()) pointer.handle(Json.obj("state", "leave", "x", .5, "y", .5));
        wasConnected = connected;
        sound.refresh();
        if (app.getVisibility() == View.VISIBLE) app.refresh();
    }

    // Sprache und PC verdrahten: Schlüssel, Werkzeuge, Sprechblasen, Aufwachen und Schlafen.

    private void wireVoice() {
        voice.requestToken = done -> link.request(Json.obj("command", "realtimeToken"), reply -> done.accept(reply == null ? null : Json.str(reply, "text")));
        voice.runTool = (name, arguments, done) -> link.request(Json.obj("command", "tool", "tool", name, "text", arguments), reply -> {
            if (reply == null) done.done("Der PC hat nicht geantwortet.", null);
            else {
                String text = Json.str(reply, "text");
                done.done(text == null ? "Das Werkzeug ist fehlgeschlagen." : text, Json.str(reply, "image"));
            }
        });
        voice.desktopSend = link::send;
        voice.onSessionStart = () -> {
            store.start();
            if (store.currentID != null) voice.recorder.start(store.currentID);
        };
        voice.resumeContext = () -> store.recentText(6000);
        voice.recorder.onChunk = chunk -> {
            store.addPending(chunk.sessionID, chunk.index, chunk.started);
            notes.upload(chunk.sessionID, chunk.index, chunk.started);
        };
        store.onSync = notes::send;
        voice.onSessionEnd = store::end;
        voice.onUserTurn = store::placeholder;
        voice.onUserWords = store::heard;
        voice.onReply = store::reply;
        voice.onReport = store::report;
        voice.onCaption = (text, finished) -> {
            // Im PC-Modus zeigt der PC die Sprechblase; bei der lokalen KI macht er das schon selbst.
            if (!voice.phoneSession() && !voice.localSession() && link.connected) {
                link.send(Json.obj("command", finished ? "captionDone" : "caption", "text", text));
            }
            if (voice.phoneSession() || !link.connected) bubble.show(text.isEmpty() ? null : text, finished);
        };
        voice.onProblem = text -> bubble.show(text, true);
        voice.onResearchStart = question -> report.loading(question);
        voice.onReportCard = r -> { if (r == null) report.failed(); else report.show(r); };
        voice.onStateChange = state -> {
            indicator.setState(state);
            sound.refresh();
            if (app.getVisibility() == View.VISIBLE) app.refresh();
            FaceAnimator a = face.animator;
            switch (state) {
                case ASLEEP:
                    a.awake = false;
                    a.localMood = null;
                    link.send(Json.obj("command", "asleep"));
                    break;
                case WAKING:
                    a.awake = true;
                    a.localMood = Mood.HAPPY;
                    break;
                case LISTENING:
                    a.awake = true;
                    a.localMood = null;
                    link.send(Json.obj("command", "awake"));
                    break;
                case ASKING:
                    a.awake = true;
                    a.localMood = Mood.LISTENING;  // ganz Ohr, solange du hältst
                    link.send(Json.obj("command", "awake"));
                    break;
                case THINKING:
                    a.localMood = Mood.THINKING;
                    break;
                case SPEAKING:
                    a.localMood = Mood.TALKING;
                    break;
            }
        };
    }

    // Mikrofon

    private boolean hasMic() { return checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED; }

    private void askMic() { requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1); }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(code, permissions, grants);
        if (code != 1) return;
        if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            if (canTalk()) voice.wake();
        } else {
            bubble.show("Ich brauche das Mikrofon. Erlaube es für Bluey in den Android-Einstellungen.", true);
        }
    }

    // Dialoge

    private void manualAddress() {
        EditText input = new EditText(this);
        input.setHint("192.168.1.20:52700");
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this, R.style.DialogTheme)
            .setTitle("PC-Adresse")
            .setMessage("Die IP-Adresse und den Port zeigt Bluey auf dem PC im Tray-Menü an. Die Verbindung ist "
                + "unverschlüsselt, also nur in vertrauenswürdigen WLANs nutzen.")
            .setView(input)
            .setPositiveButton("Verbinden", (d, w) -> {
                String value = input.getText().toString().trim();
                int colon = value.lastIndexOf(':');
                try {
                    int port = colon > 0 ? Integer.parseInt(value.substring(colon + 1)) : 52700;
                    String host = colon > 0 ? value.substring(0, colon) : value;
                    if (host.isEmpty() || port < 1 || port > 65535) throw new IllegalArgumentException();
                    link.manual(host, port);
                } catch (Exception e) {
                    Toast.makeText(this, "Bitte Adresse und Port eingeben, z. B. 192.168.1.20:52700", Toast.LENGTH_LONG).show();
                }
            })
            .setNegativeButton("Abbrechen", null).show();
    }

    private void voiceSettings() {
        int pad = Ui.dp(this, 20);
        LinearLayout fields = new LinearLayout(this);
        fields.setOrientation(LinearLayout.VERTICAL);
        fields.setPadding(pad, pad / 2, pad, 0);
        RadioGroup mode = new RadioGroup(this);
        RadioButton pc = new RadioButton(this);
        pc.setId(View.generateViewId());
        pc.setText("Mit PC (KI läuft auf dem PC – Ollama, kostenlos)");
        RadioButton phone = new RadioButton(this);
        phone.setId(View.generateViewId());
        phone.setText("Nur Handy (eigener OpenAI-Schlüssel nötig)");
        mode.addView(pc);
        mode.addView(phone);
        mode.check(settings.phoneMode() ? phone.getId() : pc.getId());
        fields.addView(mode);
        CheckBox spoken = new CheckBox(this);
        spoken.setText("Antworten laut vorlesen (Android-Stimme)");
        spoken.setChecked(settings.spokenReplies());
        fields.addView(spoken);
        TextView help = new TextView(this);
        help.setText(settings.hasKey()
            ? "Ein OpenAI-Schlüssel ist sicher auf dem Handy gespeichert. Leer lassen, um ihn zu behalten."
            : "Optional, nur für „Nur Handy“: dein OpenAI-Schlüssel. Er wird verschlüsselt auf dem Handy gespeichert. Es fallen OpenAI-Kosten an.");
        help.setPadding(0, pad / 2, 0, 0);
        fields.addView(help);
        EditText key = new EditText(this);
        key.setHint("sk-…");
        key.setSingleLine(true);
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setSaveEnabled(false);
        fields.addView(key);
        AlertDialog dialog = new AlertDialog.Builder(this, R.style.DialogTheme)
            .setTitle("Einstellungen")
            .setView(fields)
            .setPositiveButton("Speichern", null)
            .setNeutralButton("Schlüssel löschen", (d, w) -> { settings.remove(); Toast.makeText(this, "Schlüssel gelöscht.", Toast.LENGTH_SHORT).show(); })
            .setNegativeButton("Abbrechen", null)
            .create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                String entered = key.getText().toString().trim();
                if (!entered.isEmpty()) settings.save(entered);
                boolean phoneMode = mode.getCheckedRadioButtonId() == phone.getId();
                if (phoneMode && !settings.hasKey()) {
                    Toast.makeText(this, "Für „Nur Handy“ brauche ich einen OpenAI-Schlüssel.", Toast.LENGTH_LONG).show();
                    return;
                }
                if (phoneMode != settings.phoneMode()) voice.sleep();
                settings.configure(phoneMode, spoken.isChecked());
                key.setText("");
                linkChanged();
                dialog.dismiss();
            } catch (Exception e) {
                Toast.makeText(this, "Der Schlüssel ließ sich nicht sicher speichern.", Toast.LENGTH_LONG).show();
            }
        }));
        dialog.show();
        if (dialog.getWindow() != null) dialog.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
    }

    // Lebenszyklus

    @Override protected void onStart() {
        super.onStart();
        if (multicast != null && !multicast.isHeld()) multicast.acquire();
        link.start();
        started = true;
        linkChanged();
    }

    @Override protected void onStop() {
        // Im Hintergrund darf Android das Mikro nicht halten: Sitzung beenden, Verbindung schließen.
        started = false;
        ui.removeCallbacks(holdStart);
        holdingToAsk = false;
        voice.sleep();
        link.stop();
        store.save();
        if (multicast != null && multicast.isHeld()) multicast.release();
        super.onStop();
    }

    @Override protected void onDestroy() {
        voice.destroy();
        speech.destroy();
        link.destroy();
        super.onDestroy();
    }
}
