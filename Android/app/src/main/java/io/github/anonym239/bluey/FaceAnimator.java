package io.github.anonym239.bluey;

import java.util.Random;
import java.util.function.DoubleSupplier;

/**
 * Glättet, was der Computer vorgibt, zu lebendiger Bewegung: huschende Augen, Brauen,
 * Blinzeln, Neigen, kleine Hüpfer. Wird nur vom UI-Thread benutzt.
 */
final class FaceAnimator {
    /** Eine winzige gedämpfte Feder, damit jedes Teil des Gesichts ein bisschen lebt. */
    static final class Spring {
        double value, velocity;
        final double stiffness, damping;  // damping 1 = kein Überschwingen, kleiner = federnder

        Spring(double value, double stiffness, double damping) {
            this.value = value;
            this.stiffness = stiffness;
            this.damping = damping;
        }

        void step(double target, double dt) {
            double c = 2 * Math.sqrt(stiffness) * damping;
            velocity += (stiffness * (target - value) - c * velocity) * dt;
            value += velocity * dt;
        }
    }

    static final class Frame {
        double gazeX, gazeY;
        Mood mood;
        double talk;
        double closed;      // 0 offen … 1 zu (Blinzeln)
        double breathe;
        double time;
        double pupil;       // Pupillengröße
        double browLift;    // + hebt die Brauen (Design-Pixel)
        double browTilt;    // + besorgt/neugierig, - konzentriert (Radiant)
        double lean;        // Kopfneigung Richtung Blick (Radiant)
        double hop;         // kleiner Hüpfer (Design-Pixel, nach oben +)
        double blush;       // 0…1
        double squint;      // 0…1 fröhliches Zusammenkneifen von unten
    }

    private final Random random = new Random();
    private double targetGazeX, targetGazeY, targetTalk;
    private Mood targetMood = Mood.LISTENING;
    private double lastPacket = -100;
    private final Spring gazeX = new Spring(0, 260, .82);
    private final Spring gazeY = new Spring(0, 260, .82);
    private final Spring pupil = new Spring(1, 160, .5);
    private final Spring browLift = new Spring(0, 180, .55);
    private final Spring browTilt = new Spring(0, 150, .6);
    private final Spring lean = new Spring(0, 60, .8);
    private final Spring hop = new Spring(0, 260, .35);
    private final Spring blush = new Spring(.25, 40, 1);
    private final Spring squint = new Spring(0, 150, .7);
    private double talk;
    private Mood mood = Mood.LISTENING;
    private double blinkStart = -1;
    private boolean doubleBlink;
    private double nextBlink = 2;
    private double lastTime = Double.NaN;
    private double nextSaccade;
    private double wanderX = 0, wanderY = -.3;
    private double jitterX, jitterY;
    private double nextJitter;
    private double nextHop = 6;

    /** Gesetzt, solange ein Finger auf dem Bildschirm liegt (−1…1). */
    Double touchX, touchY;
    /** Stimmung vom Handy selbst (Aufwachen, Antworten). */
    Mood localMood;
    /** Lautstärke des Zwitscherns auf diesem Handy, 0…1. */
    DoubleSupplier localTalk = () -> 0;
    /** Wach und im Gespräch. Im Folgemodus kleben die Augen an deiner Maus. */
    boolean awake;

    void receive(double gx, double gy, Mood mood, double talk, double now) {
        targetGazeX = gx;
        targetGazeY = gy;
        targetMood = mood;
        targetTalk = talk;
        lastPacket = now;
    }

    /** True, solange der Computer das Gesicht steuert. */
    boolean live(double now) { return now - lastPacket < 2.5; }

    private double rand(double lo, double hi) { return lo + random.nextDouble() * (hi - lo); }

    Frame step(double now) {
        double dt = Double.isNaN(lastTime) ? 0 : Math.min(now - lastTime, 1.0 / 20);
        if (dt < 0) dt = 0;
        lastTime = now;

        boolean live = live(now);
        Mood wanted = localMood != null ? localMood : (live ? targetMood : Mood.LISTENING);
        if (wanted != mood) {
            mood = wanted;
            blinkStart = now;  // bei jedem Stimmungswechsel blinzeln
            if (mood != Mood.SLEEPY && mood != Mood.RESTING) {
                hop.velocity += 260;  // und ein kleiner Überraschungshüpfer
                pupil.velocity += 3;
            }
        }

        // Wohin er schaut, plus winzige Augenbewegungen, damit die Augen nie ganz stillstehen.
        double wantX, wantY;
        if (touchX != null && touchY != null) {
            wantX = touchX; wantY = touchY;
        } else if (live) {
            wantX = targetGazeX; wantY = targetGazeY;
        } else {
            if (now > nextSaccade) {
                wanderX = rand(-.9, .9);
                wanderY = rand(-.9, .4);
                nextSaccade = now + rand(.6, 2.2);
            }
            wantX = wanderX; wantY = wanderY;
        }
        if (mood == Mood.THINKING) { wantX = .6 + .08 * Math.sin(now * 1.3); wantY = -.85; }
        if (now > nextJitter) {
            double amount = !awake ? .015 : (mood == Mood.TALKING ? .07 : mood == Mood.THINKING ? .05 : .02);
            jitterX = rand(-amount, amount);
            jitterY = rand(-amount, amount);
            nextJitter = now + rand(.5, 1.4);
        }
        gazeX.step(wantX + jitterX, dt);
        gazeY.step(wantY + jitterY, dt);

        double wantTalk = live ? targetTalk
            : (localMood == Mood.TALKING ? .5 + .5 * Math.sin(now * 19) * Math.sin(now * 7.3) : 0);
        wantTalk = Math.max(wantTalk, localTalk.getAsDouble());
        talk += (wantTalk - talk) * Math.min(1, dt * 25);

        double wantPupil = 1, wantLift = 0, wantTilt = 0, wantBlush = .25, wantSquint = 0;
        switch (mood) {
            case LISTENING: wantPupil = 1.12; wantLift = 10; break;
            case TALKING: wantPupil = 1.05; wantLift = 6 + talk * 18; wantTilt = .05 * Math.sin(now * 2.3); break;
            case POINTING: wantPupil = .95; wantLift = -4; wantTilt = -.14; break;
            case THINKING: wantPupil = .9; wantLift = 4; wantTilt = .22; break;
            case HAPPY: wantPupil = 1.2; wantLift = 16; wantBlush = .85; wantSquint = 1; break;
            case RESTING: wantPupil = .9; wantLift = -8; wantBlush = .15; break;
            case SLEEPY: wantPupil = .88; wantLift = -10; wantTilt = .12; wantBlush = .15; break;
        }
        pupil.step(wantPupil, dt);
        browLift.step(wantLift, dt);
        browTilt.step(wantTilt, dt);
        blush.step(wantBlush, dt);
        squint.step(wantSquint, dt);
        lean.step(-gazeX.value * .045, dt);

        // Ab und zu ein fröhlicher kleiner Hüpfer, wenn sonst nichts los ist.
        if (now > nextHop) {
            if (talk < .05 && mood != Mood.SLEEPY && mood != Mood.RESTING) hop.velocity += rand(180, 320);
            nextHop = now + rand(7, 14);
        }
        hop.step(0, dt);

        // Blinzeln, manchmal doppelt. Wenn er müde ist, langsam und schwer.
        boolean drowsy = mood == Mood.SLEEPY;
        if (now > nextBlink) {
            blinkStart = now;
            doubleBlink = !drowsy && random.nextDouble() < .25;
            nextBlink = now + (drowsy ? rand(1.6, 3.0) : rand(2.0, 5.0));
        }
        double p = (now - blinkStart) / (drowsy ? .7 : .15);
        double closed = p >= 0 && p <= 1 ? Math.sin(Math.PI * p) : 0;
        if (doubleBlink && p >= 1.3 && p <= 2.3) closed = Math.sin(Math.PI * (p - 1.3));

        Frame f = new Frame();
        f.gazeX = gazeX.value;
        f.gazeY = gazeY.value;
        f.mood = mood;
        f.talk = talk;
        f.closed = closed;
        f.breathe = Math.sin(now * (mood == Mood.RESTING ? 1.1 : 1.8));
        f.time = now;
        f.pupil = pupil.value;
        f.browLift = browLift.value;
        f.browTilt = browTilt.value;
        f.lean = lean.value;
        f.hop = hop.value;
        f.blush = blush.value;
        f.squint = Math.max(0, Math.min(1, squint.value));
        return f;
    }
}
