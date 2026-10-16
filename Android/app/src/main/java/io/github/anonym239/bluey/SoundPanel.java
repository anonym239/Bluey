package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import java.util.List;
import java.util.Locale;

/**
 * Ein winziger, leiser Lautsprecher-Knopf oben rechts. Antippen: Zwitscher-Lautstärke, ein Test-Hallo
 * und mit welchem PC gekoppelt wird. Klappt nach ein paar ruhigen Sekunden wieder zu.
 */
final class SoundPanel extends LinearLayout {
    interface Host {
        double volume();
        void setVolume(double v);
        LiveVoice.State state();
        void sayHi();
        DesktopLink link();
        boolean phoneMode();
        void manual();
        void settings();
        boolean spoken();
        void setSpoken(boolean on);
        void chooseModel();
    }

    private final Host host;
    private final Icons.Button toggle;
    private final LinearLayout panel;
    private final TextView percent, hint;
    private final android.widget.CheckBox spoken;
    private final SeekBar slider;
    private final LinearLayout hi;
    private final LinearLayout desktops;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable tuck = this::close;
    private boolean open;

    SoundPanel(Context c, Host host) {
        super(c);
        this.host = host;
        setOrientation(VERTICAL);
        setGravity(Gravity.END);
        toggle = new Icons.Button(c, Icons.Kind.SPEAKER);
        toggle.setContentDescription("Ton-Einstellungen");
        toggle.setOnClickListener(v -> { if (open) close(); else open(); });
        addView(toggle, new LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44)));

        panel = new LinearLayout(c);
        panel.setOrientation(VERTICAL);
        int pad = Ui.dp(c, 16);
        panel.setPadding(pad, pad, pad, pad);
        panel.setBackground(Ui.round(Palette.alpha(Palette.PANEL, .95), 18, c));
        LinearLayout head = new LinearLayout(c);
        head.addView(Ui.label(c, "Zwitscher-Lautstärke"), new LayoutParams(0, -2, 1));
        percent = Ui.text(c, "", Fonts.mono, 13, Color.WHITE);
        head.addView(percent);
        panel.addView(head);
        slider = new SeekBar(c);
        slider.setMax(100);
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int value, boolean user) {
                if (user) { host.setVolume(value / 100.0); poke(); refresh(); }
            }
            @Override public void onStartTrackingTouch(SeekBar s) { poke(); }
            @Override public void onStopTrackingTouch(SeekBar s) { poke(); }
        });
        panel.addView(slider);
        hi = Ui.button(c, null, "Hallo sagen", Fonts.sansBold, 15, Ui.berry(12, c));
        hi.setOnClickListener(v -> { host.sayHi(); poke(); });
        LayoutParams hiParams = new LayoutParams(-1, -2);
        hiParams.topMargin = Ui.dp(c, 8);
        panel.addView(hi, hiParams);
        desktops = new LinearLayout(c);
        desktops.setOrientation(VERTICAL);
        panel.addView(desktops);
        spoken = new android.widget.CheckBox(c);
        spoken.setText("Antworten laut vorlesen");
        spoken.setTextColor(Color.WHITE);
        spoken.setTypeface(Fonts.sans);
        spoken.setOnCheckedChangeListener((b, on) -> { if (on != host.spoken()) { host.setSpoken(on); poke(); } });
        LayoutParams spokenParams = new LayoutParams(-1, -2);
        spokenParams.topMargin = Ui.dp(c, 6);
        panel.addView(spoken, spokenParams);
        hint = Ui.text(c, "", Fonts.sans, 12, Palette.INK_SOFT);
        hint.setPadding(0, Ui.dp(c, 8), 0, 0);
        panel.addView(hint);
        LinearLayout extras = new LinearLayout(c);
        extras.setPadding(0, Ui.dp(c, 8), 0, 0);
        TextView manual = link(c, "IP eingeben");
        manual.setOnClickListener(v -> { close(); host.manual(); });
        TextView model = link(c, "KI-Modell");
        model.setOnClickListener(v -> { close(); host.chooseModel(); });
        extras.addView(model, new LayoutParams(0, -2, 1));
        TextView settings = link(c, "Einstellungen");
        settings.setOnClickListener(v -> { close(); host.settings(); });
        extras.addView(manual, new LayoutParams(0, -2, 1));
        extras.addView(settings);
        panel.addView(extras);
        LayoutParams panelParams = new LayoutParams(Ui.dp(c, 270), -2);
        panelParams.topMargin = Ui.dp(c, 6);
        addView(panel, panelParams);
        panel.setVisibility(GONE);
        refresh();
    }

    private static TextView link(Context c, String text) {
        TextView t = Ui.text(c, text, Fonts.sansBold, 13, Palette.BERRY1);
        t.setPadding(0, Ui.dp(c, 6), 0, Ui.dp(c, 6));
        return t;
    }

    boolean isOpen() { return open; }

    void open() {
        open = true;
        panel.setVisibility(VISIBLE);
        panel.setAlpha(0);
        panel.setScaleX(.9f);
        panel.setScaleY(.9f);
        panel.setPivotX(Ui.dp(getContext(), 270));
        panel.setPivotY(0);
        panel.animate().alpha(1).scaleX(1).scaleY(1).setDuration(220).start();
        refresh();
        poke();
    }

    void close() {
        open = false;
        ui.removeCallbacks(tuck);
        panel.animate().alpha(0).setDuration(200).withEndAction(() -> { if (!open) panel.setVisibility(GONE); }).start();
        refresh();
    }

    /** Nach ein paar ruhigen Sekunden wegklappen, damit es nie im Bild bleibt. */
    private void poke() {
        ui.removeCallbacks(tuck);
        ui.postDelayed(tuck, 6000);
    }

    void refresh() {
        double volume = host.volume();
        Icons.Kind icon = open ? Icons.Kind.CLOSE : volume < .01 ? Icons.Kind.SPEAKER_OFF : Icons.Kind.SPEAKER;
        toggle.set(icon, open ? 0xE6FFFFFF : 0x59FFFFFF, open ? 0x24FFFFFF : 0x0FFFFFFF);
        percent.setText(String.format(Locale.ROOT, "%d %%", Math.round(volume * 100)));
        slider.setProgress((int) Math.round(volume * 100));
        spoken.setChecked(host.spoken());
        boolean asleep = host.state() == LiveVoice.State.ASLEEP;
        ((TextView) hi.getChildAt(hi.getChildCount() - 1)).setText(asleep ? "Weck ihn auf" : "Hallo sagen");
        DesktopLink link = host.link();
        boolean usable = link.connected || host.phoneMode();
        hi.setEnabled(usable);
        hi.setAlpha(usable ? 1 : .4f);
        desktops.removeAllViews();
        List<String> names = link.desktops();
        if (!names.isEmpty()) {
            TextView label = Ui.label(getContext(), "PC");
            label.setPadding(0, Ui.dp(getContext(), 12), 0, Ui.dp(getContext(), 2));
            desktops.addView(label);
            for (String name : names) desktops.addView(desktopRow(name, link));
        }
        hint.setText(host.phoneMode() ? "Nur-Handy-Modus: Ich rede direkt mit OpenAI."
            : link.connected ? "Verbunden mit " + (link.desktopName != null ? link.desktopName : link.current) + "."
            : "Verbinde dich mit deinem PC, um mit ihm zu reden.");
    }

    private View desktopRow(String name, DesktopLink link) {
        LinearLayout row = new LinearLayout(getContext());
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Ui.dp(getContext(), 36));
        TextView t = Ui.text(getContext(), name, Fonts.sans, 14, Color.WHITE);
        t.setSingleLine(true);
        row.addView(t, new LayoutParams(0, -2, 1));
        if (name.equals(link.current)) {
            row.addView(new Ui.IconView(getContext(), link.connected ? Icons.Kind.CHECK : Icons.Kind.DOTS, Palette.BERRY2, 16),
                new LayoutParams(Ui.dp(getContext(), 22), Ui.dp(getContext(), 22)));
        }
        row.setOnClickListener(v -> { link.choose(name); poke(); });
        return row;
    }
}
