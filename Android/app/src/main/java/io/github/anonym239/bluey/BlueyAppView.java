package io.github.anonym239.bluey;

import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * Blueys eigener App-Bildschirm: Sitzung starten oder beenden, frühere Sitzungen und ihre Transkripte,
 * Einstellungen. Geöffnet über den dezenten Knopf oben rechts auf seinem Gesicht.
 */
final class BlueyAppView extends FrameLayout {
    interface Host {
        LiveVoice.State state();
        void toggleSession();
        boolean canStart();
        DesktopLink link();
        double volume();
        void setVolume(double v);
        void close();
        void settings();
        boolean phoneMode();
        boolean spoken();
        void setSpoken(boolean on);
        void chooseModel();
    }

    private final SessionStore store;
    private final Host host;
    private final LinearLayout list;
    private final TextView count, status, hint;
    private final LinearLayout startButton;
    private final View dot;
    private final SeekBar volume;
    private final android.widget.Switch spokenSwitch;
    private final FrameLayout detailHolder;
    private String openSession;
    private final Runnable observer = this::refresh;

    BlueyAppView(Context c, SessionStore store, Host host) {
        super(c);
        this.store = store;
        this.host = host;
        setBackgroundColor(Color.BLACK);
        setClickable(true);

        LinearLayout split = new LinearLayout(c);
        split.setOrientation(LinearLayout.HORIZONTAL);
        addView(split, new LayoutParams(-1, -1));

        // Links: wer er ist, Start/Ende, Einstellungen.
        ScrollView sideScroll = new ScrollView(c);
        sideScroll.setBackgroundColor(Palette.alpha(Palette.PANEL, .6));
        LinearLayout side = new LinearLayout(c);
        side.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(c, 22);
        side.setPadding(pad, pad, pad, pad);
        sideScroll.addView(side);
        split.addView(sideScroll, new LinearLayout.LayoutParams(Ui.dp(c, 300), -1));

        LinearLayout who = new LinearLayout(c);
        who.setGravity(Gravity.CENTER_VERTICAL);
        who.addView(new Ui.MiniBluey(c), new LinearLayout.LayoutParams(Ui.dp(c, 54), Ui.dp(c, 48)));
        LinearLayout names = new LinearLayout(c);
        names.setOrientation(LinearLayout.VERTICAL);
        names.setPadding(Ui.dp(c, 12), 0, 0, 0);
        names.addView(Ui.text(c, "Bluey", Fonts.display, 26, Color.WHITE));
        LinearLayout statusRow = new LinearLayout(c);
        statusRow.setGravity(Gravity.CENTER_VERTICAL);
        dot = new View(c);
        statusRow.addView(dot, new LinearLayout.LayoutParams(Ui.dp(c, 7), Ui.dp(c, 7)));
        status = Ui.text(c, "", Fonts.sans, 12, Palette.INK_SOFT);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        status.setPadding(Ui.dp(c, 6), 0, 0, 0);
        statusRow.addView(status);
        names.addView(statusRow);
        who.addView(names);
        side.addView(who);

        startButton = Ui.button(c, Icons.Kind.PLAY, "Sitzung starten", Fonts.display, 18, Ui.berry(16, c));
        startButton.setMinimumHeight(Ui.dp(c, 50));
        startButton.setOnClickListener(v -> host.toggleSession());
        LinearLayout.LayoutParams startParams = new LinearLayout.LayoutParams(-1, -2);
        startParams.topMargin = Ui.dp(c, 18);
        side.addView(startButton, startParams);
        hint = Ui.text(c, "", Fonts.sans, 12, Palette.INK_SOFT);
        hint.setPadding(0, Ui.dp(c, 10), 0, Ui.dp(c, 14));
        side.addView(hint);
        View divider = new View(c);
        divider.setBackgroundColor(0x14FFFFFF);
        side.addView(divider, new LinearLayout.LayoutParams(-1, 1));
        TextView volumeLabel = Ui.label(c, "Zwitscher-Lautstärke");
        volumeLabel.setPadding(0, Ui.dp(c, 16), 0, Ui.dp(c, 4));
        side.addView(volumeLabel);
        volume = new SeekBar(c);
        volume.setMax(100);
        volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int value, boolean user) { if (user) host.setVolume(value / 100.0); }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });
        side.addView(volume);
        spokenSwitch = new android.widget.Switch(c);
        spokenSwitch.setText("Antworten laut vorlesen");
        spokenSwitch.setTextColor(Color.WHITE);
        spokenSwitch.setTypeface(Fonts.sans);
        spokenSwitch.setPadding(0, Ui.dp(c, 12), 0, 0);
        spokenSwitch.setOnCheckedChangeListener((b, on) -> { if (on != host.spoken()) host.setSpoken(on); });
        side.addView(spokenSwitch);
        LinearLayout model = Ui.button(c, Icons.Kind.SPARKLES, "KI-Modell am PC", Fonts.sansBold, 15, Ui.round(0x14FFFFFF, 14, c));
        model.setOnClickListener(v -> host.chooseModel());
        LinearLayout.LayoutParams modelParams = new LinearLayout.LayoutParams(-1, -2);
        modelParams.topMargin = Ui.dp(c, 18);
        side.addView(model, modelParams);
        LinearLayout settings = Ui.button(c, Icons.Kind.GEAR, "Einstellungen", Fonts.sansBold, 15, Ui.round(0x14FFFFFF, 14, c));
        settings.setOnClickListener(v -> host.settings());
        LinearLayout.LayoutParams settingsParams = new LinearLayout.LayoutParams(-1, -2);
        settingsParams.topMargin = Ui.dp(c, 10);
        side.addView(settings, settingsParams);
        LinearLayout back = Ui.button(c, Icons.Kind.SMILE, "Zurück zu seinem Gesicht", Fonts.sansBold, 15, Ui.round(0x14FFFFFF, 14, c));
        back.setOnClickListener(v -> host.close());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(-1, -2);
        backParams.topMargin = Ui.dp(c, 10);
        side.addView(back, backParams);

        // Rechts: Sitzungen.
        LinearLayout right = new LinearLayout(c);
        right.setOrientation(LinearLayout.VERTICAL);
        LinearLayout head = new LinearLayout(c);
        head.setGravity(Gravity.CENTER_VERTICAL);
        head.setPadding(pad, Ui.dp(c, 20), pad, Ui.dp(c, 8));
        head.addView(Ui.text(c, "Sitzungen", Fonts.display, 24, Color.WHITE), new LinearLayout.LayoutParams(0, -2, 1));
        count = Ui.text(c, "", Fonts.mono, 13, Palette.INK_SOFT);
        head.addView(count);
        right.addView(head);
        ScrollView listScroll = new ScrollView(c);
        list = new LinearLayout(c);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(Ui.dp(c, 16), 0, Ui.dp(c, 16), Ui.dp(c, 24));
        listScroll.addView(list);
        right.addView(listScroll, new LinearLayout.LayoutParams(-1, 0, 1));
        split.addView(right, new LinearLayout.LayoutParams(0, -1, 1));

        detailHolder = new FrameLayout(c);
        detailHolder.setBackgroundColor(Color.BLACK);
        detailHolder.setClickable(true);
        detailHolder.setVisibility(GONE);
        addView(detailHolder, new LayoutParams(-1, -1));
    }

    @Override protected void onAttachedToWindow() { super.onAttachedToWindow(); store.observe(observer); }
    @Override protected void onDetachedFromWindow() { store.unobserve(observer); super.onDetachedFromWindow(); }

    /** Zurück: aus einer Sitzung zur Liste. False, wenn schon in der Liste. */
    boolean back() {
        if (openSession == null) return false;
        openSession = null;
        detailHolder.setVisibility(GONE);
        detailHolder.removeAllViews();
        return true;
    }

    void refresh() {
        if (getVisibility() != VISIBLE) return;
        Context c = getContext();
        DesktopLink link = host.link();
        boolean asleep = host.state() == LiveVoice.State.ASLEEP;
        GradientDrawable dotShape = new GradientDrawable();
        dotShape.setShape(GradientDrawable.OVAL);
        dotShape.setColor(link.connected || host.phoneMode() ? Palette.GREEN : Palette.alpha(Palette.INK_SOFT, .5));
        dot.setBackground(dotShape);
        status.setText(host.phoneMode() ? "Nur Handy (OpenAI)" : link.connected
            ? (link.desktopName != null ? link.desktopName : link.current) : "Suche deinen PC");
        ((Ui.IconView) startButton.getChildAt(0)).set(asleep ? Icons.Kind.PLAY : Icons.Kind.STOP, Color.WHITE);
        ((TextView) startButton.getChildAt(2)).setText(asleep ? "Sitzung starten" : "Sitzung beenden");
        startButton.setBackground(asleep ? Ui.berry(16, c) : Ui.round(Palette.RED, 16, c));
        boolean disabled = asleep && !host.canStart();
        startButton.setEnabled(!disabled);
        startButton.setAlpha(disabled ? .5f : 1);
        hint.setText(asleep ? "Er hört die ganze Sitzung zu. Halte sein Gesicht gedrückt, um etwas zu fragen; lass los, und er antwortet."
            : "Sitzung läuft. Halte sein Gesicht gedrückt, um zu fragen; alles Gesagte wird hier gespeichert.");
        volume.setProgress((int) Math.round(host.volume() * 100));
        spokenSwitch.setChecked(host.spoken());

        count.setText(String.valueOf(store.sessions.size()));
        list.removeAllViews();
        if (store.sessions.isEmpty()) {
            LinearLayout empty = new LinearLayout(c);
            empty.setOrientation(LinearLayout.VERTICAL);
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(0, Ui.dp(c, 60), 0, 0);
            empty.addView(new Ui.IconView(c, Icons.Kind.BUBBLE, Palette.BERRY2, 34), new LinearLayout.LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44)));
            empty.addView(Ui.text(c, "Noch keine Sitzungen", Fonts.display, 18, Color.WHITE));
            empty.addView(Ui.text(c, "Starte eine, dann erscheinen hier dein Transkript und seine Antworten.", Fonts.sans, 13, Palette.INK_SOFT));
            list.addView(empty);
        } else {
            for (BlueySession s : store.sessions) list.addView(row(s));
        }
        if (openSession != null) {
            if (store.find(openSession) == null) back(); else showDetail(openSession);
        }
    }

    private View row(BlueySession s) {
        Context c = getContext();
        LinearLayout row = new LinearLayout(c);
        row.setGravity(Gravity.CENTER_VERTICAL);
        int pad = Ui.dp(c, 14);
        row.setPadding(pad, Ui.dp(c, 10), pad, Ui.dp(c, 10));
        row.setBackground(Ui.round(Palette.PANEL, 14, c));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = Ui.dp(c, 8);
        row.setLayoutParams(params);
        LinearLayout left = new LinearLayout(c);
        left.setOrientation(LinearLayout.VERTICAL);
        LinearLayout top = new LinearLayout(c);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.addView(Ui.text(c, BlueySession.formatDate(s.started), Fonts.sansBold, 15, Color.WHITE));
        if (s.id.equals(store.currentID)) {
            TextView live = Ui.text(c, "LIVE", Fonts.monoMedium, 10, Color.BLACK);
            live.setPadding(Ui.dp(c, 6), Ui.dp(c, 1), Ui.dp(c, 6), Ui.dp(c, 1));
            live.setBackground(Ui.round(Palette.GREEN, 8, c));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.leftMargin = Ui.dp(c, 8);
            top.addView(live, lp);
        }
        left.addView(top);
        TextView summary = Ui.text(c, s.summary(), Fonts.sans, 13, Palette.INK_SOFT);
        summary.setSingleLine(true);
        summary.setEllipsize(TextUtils.TruncateAt.END);
        left.addView(summary);
        row.addView(left, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout meta = new LinearLayout(c);
        meta.setOrientation(LinearLayout.VERTICAL);
        meta.setGravity(Gravity.END);
        meta.addView(Ui.text(c, BlueySession.formatDuration(s.duration(SessionStore.now())), Fonts.mono, 12, Palette.INK_SOFT));
        meta.addView(Ui.text(c, s.questionCount() + " gefragt", Fonts.mono, 11, Palette.BERRY1));
        row.addView(meta);
        row.setOnClickListener(v -> showDetail(s.id));
        row.setOnLongClickListener(v -> {
            new AlertDialog.Builder(c, R.style.DialogTheme).setTitle("Sitzung löschen?")
                .setMessage(BlueySession.formatDate(s.started) + " wird vom Handy gelöscht. Meeting-Notizen auf dem PC bleiben.")
                .setPositiveButton("Löschen", (d, w) -> store.delete(s.id))
                .setNegativeButton("Abbrechen", null).show();
            return true;
        });
        return row;
    }

    // Eine Sitzung als Chat: was gesagt wurde in Grau, deine Fragen in Blau, seine Antworten in weißen Blasen.

    private void showDetail(String id) {
        BlueySession s = store.find(id);
        if (s == null) return;
        openSession = id;
        Context c = getContext();
        detailHolder.removeAllViews();
        LinearLayout page = new LinearLayout(c);
        page.setOrientation(LinearLayout.VERTICAL);
        LinearLayout head = new LinearLayout(c);
        head.setGravity(Gravity.CENTER_VERTICAL);
        int pad = Ui.dp(c, 22);
        head.setPadding(pad, Ui.dp(c, 12), pad, Ui.dp(c, 12));
        Icons.Button backButton = new Icons.Button(c, Icons.Kind.BACK);
        backButton.set(Icons.Kind.BACK, Color.WHITE, 0x14FFFFFF);
        backButton.setContentDescription("Zurück");
        backButton.setOnClickListener(v -> back());
        head.addView(backButton, new LinearLayout.LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44)));
        LinearLayout titles = new LinearLayout(c);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.setPadding(Ui.dp(c, 10), 0, 0, 0);
        titles.addView(Ui.text(c, BlueySession.formatDate(s.started), Fonts.display, 20, Color.WHITE));
        String metaText = BlueySession.formatDuration(s.duration(SessionStore.now())) + " · " + s.questionCount() + " gefragt"
            + (s.transcribing() > 0 ? " · transkribiere " + s.transcribing() + " Stück" + (s.transcribing() == 1 ? "" : "e") + " …" : "");
        titles.addView(Ui.text(c, metaText, Fonts.mono, 11, Palette.INK_SOFT));
        head.addView(titles, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout copy = Ui.button(c, Icons.Kind.COPY, "Prompt für Agent kopieren", Fonts.sansBold, 13, Ui.round(Palette.BERRY3, 20, c));
        copy.setOnClickListener(v -> copyPrompt(s, copy));
        head.addView(copy);
        Icons.Button share = new Icons.Button(c, Icons.Kind.SHARE);
        share.set(Icons.Kind.SHARE, Color.WHITE, 0x14FFFFFF);
        share.setContentDescription("Teilen");
        share.setOnClickListener(v -> {
            Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, s.exportText());
            c.startActivity(Intent.createChooser(send, "Sitzung teilen"));
        });
        LinearLayout.LayoutParams shareParams = new LinearLayout.LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44));
        shareParams.leftMargin = Ui.dp(c, 8);
        head.addView(share, shareParams);
        page.addView(head);

        ScrollView scroll = new ScrollView(c);
        LinearLayout entries = new LinearLayout(c);
        entries.setOrientation(LinearLayout.VERTICAL);
        entries.setPadding(pad, 0, pad, Ui.dp(c, 24));
        for (BlueySession.Entry e : s.displayEntries()) entries.addView(entry(e));
        scroll.addView(entries);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        detailHolder.addView(page, new LayoutParams(-1, -1));
        detailHolder.setVisibility(VISIBLE);
        scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN));
    }

    private static int speakerColor(String speaker) {
        int[] colors = {0xFF8FB3FF, 0xFF5BE49B, 0xFFFFB86B, 0xFFFF9AD0, 0xFFC79BFF, 0xFF6BE3E0};
        if (speaker == null || speaker.isEmpty() || speaker.equals("?")) return Palette.INK_SOFT;
        return colors[speaker.codePointAt(0) % colors.length];
    }

    private View entry(BlueySession.Entry e) {
        Context c = getContext();
        LinearLayout.LayoutParams spacing = new LinearLayout.LayoutParams(-1, -2);
        spacing.bottomMargin = Ui.dp(c, 10);
        switch (e.kind) {
            case TRANSCRIPT: {
                LinearLayout row = new LinearLayout(c);
                row.setLayoutParams(spacing);
                TextView who = Ui.text(c, e.speaker == null ? "Sprecher" : "Sprecher " + e.speaker, Fonts.monoMedium, 11, speakerColor(e.speaker));
                row.addView(who, new LinearLayout.LayoutParams(Ui.dp(c, 84), -2));
                row.addView(Ui.text(c, e.text, Fonts.sans, 15, 0xEBFFFFFF), new LinearLayout.LayoutParams(0, -2, 1));
                row.addView(Ui.text(c, new SimpleDateFormat("HH:mm", Locale.GERMANY).format(new Date((long) (e.time * 1000))), Fonts.mono, 10, Palette.alpha(Palette.INK_SOFT, .7)));
                return row;
            }
            case HEARD: {
                TextView t = Ui.text(c, e.text, Fonts.sans, 14, Palette.INK_SOFT);
                t.setLayoutParams(spacing);
                t.setPadding(Ui.dp(c, 4), 0, 0, 0);
                return t;
            }
            case ASKED: {
                LinearLayout col = new LinearLayout(c);
                col.setOrientation(LinearLayout.VERTICAL);
                col.setGravity(Gravity.END);
                col.setLayoutParams(spacing);
                col.setPadding(Ui.dp(c, 120), 0, 0, 0);
                col.addView(Ui.text(c, "Du hast gefragt", Fonts.mono, 10, Palette.BERRY1));
                TextView t = Ui.text(c, e.text, Fonts.sansBold, 15, Color.WHITE);
                t.setPadding(Ui.dp(c, 14), Ui.dp(c, 10), Ui.dp(c, 14), Ui.dp(c, 10));
                t.setBackground(Ui.berry(18, c));
                col.addView(t);
                return col;
            }
            case REPLY: {
                LinearLayout row = new LinearLayout(c);
                row.setGravity(Gravity.BOTTOM);
                row.setLayoutParams(spacing);
                row.setPadding(0, 0, Ui.dp(c, 120), 0);
                row.addView(new Ui.MiniBluey(c), new LinearLayout.LayoutParams(Ui.dp(c, 28), Ui.dp(c, 25)));
                TextView t = Ui.text(c, e.text, Fonts.display, 16, Palette.INK);
                t.setPadding(Ui.dp(c, 14), Ui.dp(c, 10), Ui.dp(c, 14), Ui.dp(c, 10));
                t.setBackground(Ui.round(Color.WHITE, 18, c));
                LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(-2, -2);
                tp.leftMargin = Ui.dp(c, 8);
                row.addView(t, tp);
                return row;
            }
            default: {
                String[] parts = e.text.split("\n\n", 2);
                LinearLayout card = new LinearLayout(c);
                card.setOrientation(LinearLayout.VERTICAL);
                int pad = Ui.dp(c, 14);
                card.setPadding(pad, pad, pad, pad);
                GradientDrawable bg = Ui.round(Palette.CARD, 18, c);
                bg.setStroke(Ui.dp(c, 2), Palette.BERRY2);
                card.setBackground(bg);
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
                params.setMargins(Ui.dp(c, 36), 0, Ui.dp(c, 80), Ui.dp(c, 10));
                card.setLayoutParams(params);
                LinearLayout head = new LinearLayout(c);
                head.setGravity(Gravity.CENTER_VERTICAL);
                head.addView(new Ui.IconView(c, Icons.Kind.DOC, Palette.BERRY2, 16), new LinearLayout.LayoutParams(Ui.dp(c, 22), Ui.dp(c, 22)));
                TextView title = Ui.text(c, parts[0], Fonts.display, 16, Palette.INK);
                title.setPadding(Ui.dp(c, 8), 0, 0, 0);
                head.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
                Ui.IconView toggle = new Ui.IconView(c, Icons.Kind.PLUS, Color.WHITE, 12);
                GradientDrawable circle = new GradientDrawable();
                circle.setShape(GradientDrawable.OVAL);
                circle.setColor(Palette.BERRY2);
                toggle.setBackground(circle);
                head.addView(toggle, new LinearLayout.LayoutParams(Ui.dp(c, 24), Ui.dp(c, 24)));
                card.addView(head);
                TextView body = Ui.text(c, parts.length > 1 ? parts[1] : "", Fonts.sans, 14, Palette.INK);
                body.setMaxLines(3);
                body.setEllipsize(TextUtils.TruncateAt.END);
                body.setPadding(0, Ui.dp(c, 8), 0, 0);
                card.addView(body);
                card.setOnClickListener(v -> {
                    boolean open = body.getMaxLines() == 3;
                    body.setMaxLines(open ? Integer.MAX_VALUE : 3);
                    toggle.set(open ? Icons.Kind.MINUS : Icons.Kind.PLUS, Color.WHITE);
                });
                return card;
            }
        }
    }

    /** Ein Prompt für einen Agenten (z. B. Claude Code auf dem PC), der ihn zu den Notizdateien dieser Sitzung führt. */
    private void copyPrompt(BlueySession s, LinearLayout button) {
        String root = "Dokumente\\Bluey Notizen";
        String path = s.notesPath != null ? s.notesPath
            : root + "\\ (der Ordner, der mit " + new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date((long) (s.started * 1000))) + " beginnt)";
        String prompt = "Ich habe mit meiner Bluey-App am " + new SimpleDateFormat("EEEE, d. MMMM yyyy 'um' HH:mm", Locale.GERMANY)
            .format(new Date((long) (s.started * 1000))) + " ein Meeting aufgenommen. Die Notizen liegen auf meinem PC in " + path + "\n\n"
            + "- notes.md: das ganze Transkript mit Uhrzeiten und Sprechern (A, B, … je Fünf-Minuten-Stück), dazu meine "
            + "Fragen an Bluey, seine Antworten und Rechercheberichte. Fang hier an.\n"
            + "- session.json: dieselben Daten, strukturiert.\n"
            + "- audio/: die Originalaufnahme in Fünf-Minuten-Stücken.\n\n"
            + "Alle meine Sitzungen liegen in " + root + ", ein Ordner pro Sitzung (siehe README.md dort). Lies die Notizen "
            + "und hilf mir dann mit: ";
        ClipboardManager clipboard = (ClipboardManager) getContext().getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("Bluey", prompt));
        TextView label = (TextView) button.getChildAt(2);
        ((Ui.IconView) button.getChildAt(0)).set(Icons.Kind.CHECK, Color.WHITE);
        label.setText("Kopiert");
        Toast.makeText(getContext(), "Prompt kopiert", Toast.LENGTH_SHORT).show();
        postDelayed(() -> {
            ((Ui.IconView) button.getChildAt(0)).set(Icons.Kind.COPY, Color.WHITE);
            label.setText("Prompt für Agent kopieren");
        }, 2000);
    }

    /** Für Tests der Liste. */
    List<BlueySession> sessions() { return store.sessions; }
}
