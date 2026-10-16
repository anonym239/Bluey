package io.github.anonym239.bluey;

import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Die Recherchekarte (im Modus ohne PC auf dem Handy; mit PC erscheint sie auf dem PC-Bildschirm). */
final class ReportCard extends LinearLayout {
    private final TextView title, body, more;
    private final LinearLayout sources;
    private final ScrollView scroll;
    private boolean expanded;
    private OpenAi.Report report;

    ReportCard(Context c) {
        super(c);
        setOrientation(VERTICAL);
        int pad = Ui.dp(c, 18);
        setPadding(pad, pad, pad, pad);
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.WHITE, Palette.CARD});
        bg.setCornerRadius(Ui.dp(c, 22));
        bg.setStroke(Ui.dp(c, 2.5f), Palette.BERRY2);
        setBackground(bg);
        setElevation(Ui.dp(c, 8));

        LinearLayout header = new LinearLayout(c);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(new Ui.IconView(c, Icons.Kind.SEARCH, Palette.BERRY2, 17), new LayoutParams(Ui.dp(c, 22), Ui.dp(c, 22)));
        title = Ui.text(c, "Recherche", Fonts.display, 19, Palette.INK);
        title.setPadding(Ui.dp(c, 10), 0, Ui.dp(c, 6), 0);
        header.addView(title, new LayoutParams(0, -2, 1));
        Icons.Button close = new Icons.Button(c, Icons.Kind.MINUS);
        close.set(Icons.Kind.MINUS, Color.WHITE, Palette.BERRY2);
        close.iconSize = 12;
        close.setContentDescription("Schließen");
        close.setOnClickListener(v -> setVisibility(GONE));
        header.addView(close, new LayoutParams(Ui.dp(c, 36), Ui.dp(c, 36)));
        addView(header);

        scroll = new ScrollView(c);
        LinearLayout content = new LinearLayout(c);
        content.setOrientation(VERTICAL);
        body = Ui.text(c, "", Fonts.sans, 14, Palette.INK);
        body.setPadding(0, Ui.dp(c, 8), 0, 0);
        content.addView(body);
        sources = new LinearLayout(c);
        sources.setOrientation(VERTICAL);
        content.addView(sources);
        scroll.addView(content);
        addView(scroll, new LayoutParams(-1, -2));
        more = Ui.text(c, "Tippen für mehr", Fonts.mono, 11, Palette.BERRY2);
        more.setPadding(0, Ui.dp(c, 6), 0, 0);
        addView(more);
        setOnClickListener(v -> { if (report != null) { expanded = !expanded; render(); } });
    }

    void loading(String question) {
        report = null;
        expanded = false;
        title.setText("Recherchiere");
        body.setText("Recherchiere zu „" + question + "“ …");
        body.setTextColor(0xFF5D5873);
        body.setMaxLines(2);
        sources.removeAllViews();
        more.setVisibility(GONE);
        setVisibility(VISIBLE);
    }

    void failed() {
        report = null;
        title.setText("Recherche");
        body.setText("Die Recherche kam nicht zurück.");
        more.setVisibility(GONE);
        setVisibility(VISIBLE);
    }

    void show(OpenAi.Report r) {
        report = r;
        expanded = false;
        render();
        setVisibility(VISIBLE);
    }

    private void render() {
        if (report == null) return;
        title.setText(report.title);
        body.setTextColor(Palette.INK);
        body.setText(String.join(expanded ? "\n\n" : " ", report.paragraphs));
        body.setMaxLines(expanded ? Integer.MAX_VALUE : 3);
        sources.removeAllViews();
        if (expanded && !report.sources.isEmpty()) {
            TextView label = Ui.text(getContext(), "QUELLEN", Fonts.mono, 11, 0xFF5D5873);
            label.setPadding(0, Ui.dp(getContext(), 12), 0, Ui.dp(getContext(), 4));
            sources.addView(label);
            for (String[] s : report.sources) {
                TextView link = Ui.text(getContext(), s[0], Fonts.sans, 13, Palette.BERRY3);
                link.setSingleLine(true);
                link.setPadding(0, Ui.dp(getContext(), 3), 0, Ui.dp(getContext(), 3));
                link.setOnClickListener(v -> {
                    try { getContext().startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(s[1]))); } catch (Exception ignored) {}
                });
                sources.addView(link);
            }
        }
        scroll.getLayoutParams().height = expanded ? Ui.dp(getContext(), 230) : LayoutParams.WRAP_CONTENT;
        scroll.requestLayout();
        more.setText(expanded ? "Tippen zum Einklappen" : "Tippen für mehr");
        more.setVisibility(VISIBLE);
    }
}
