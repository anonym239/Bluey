package io.github.anonym239.bluey;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * Findet den Computer (Windows oder Mac) per Bonjour (_googly._tcp) im WLAN und hält eine Verbindung offen.
 * Gleiches Protokoll wie das Original: eine JSON-Zeile pro Paket. Alle öffentlichen Methoden auf dem UI-Thread.
 */
final class DesktopLink {
    interface Listener {
        void changed();
        void face(double gazeX, double gazeY, Mood mood, double talk);
        void command(String command, JSONObject packet);
    }

    static final String SERVICE = "_googly._tcp.";
    private static final String MANUAL = "manual:";

    private final NsdManager nsd;
    private final SharedPreferences prefs;
    private final Listener listener;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newCachedThreadPool();
    private final ExecutorService writes = Executors.newSingleThreadExecutor();
    private final Map<String, NsdServiceInfo> services = new LinkedHashMap<>();
    private final Map<String, Consumer<JSONObject>> waiting = new HashMap<>();
    private final ArrayDeque<NsdServiceInfo> resolveQueue = new ArrayDeque<>();
    private NsdManager.DiscoveryListener discovery;
    private volatile Socket socket;
    private boolean active, resolving, connecting;
    private int generation, discoveryGeneration;

    /** Verbunden mit einem Computer. */
    boolean connected;
    /** Der Name, den der Computer im hello-Paket schickt. */
    String desktopName;
    /** Der Computer, mit dem das Handy verbunden ist (oder es gerade versucht). */
    String current;
    /** Der zuletzt gewählte Computer, damit das Handy beim Start zu ihm zurückfindet. */
    String preferred;

    DesktopLink(Context context, Listener listener) {
        nsd = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
        prefs = context.getSharedPreferences("bluey", Context.MODE_PRIVATE);
        preferred = prefs.getString("preferredDesktop", null);
        this.listener = listener;
    }

    /** Alle Computer mit Bluey in diesem WLAN, nach Namen. */
    List<String> desktops() {
        List<String> names = new ArrayList<>(services.keySet());
        java.util.Collections.sort(names, String.CASE_INSENSITIVE_ORDER);
        String manual = manualAddress();
        if (manual != null && !names.contains(manual)) names.add(manual);
        return names;
    }

    private String manualAddress() {
        String value = prefs.getString("manualDesktop", null);
        return value == null || value.isEmpty() ? null : value;
    }

    void start() {
        if (active) return;
        active = true;
        int run = ++discoveryGeneration;
        discovery = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) {}
            @Override public void onServiceFound(NsdServiceInfo service) {
                ui.post(() -> { if (run == discoveryGeneration && active) { resolveQueue.add(service); resolveNext(run); } });
            }
            @Override public void onServiceLost(NsdServiceInfo service) {
                ui.post(() -> {
                    if (run != discoveryGeneration) return;
                    services.remove(service.getServiceName());
                    listener.changed();
                });
            }
            @Override public void onDiscoveryStopped(String type) {}
            @Override public void onStartDiscoveryFailed(String type, int code) {
                ui.post(() -> { if (run == discoveryGeneration) { active = false; ui.postDelayed(DesktopLink.this::start, 3000); } });
            }
            @Override public void onStopDiscoveryFailed(String type, int code) {}
        };
        try {
            nsd.discoverServices(SERVICE, NsdManager.PROTOCOL_DNS_SD, discovery);
        } catch (RuntimeException e) {
            discovery = null;
        }
        connectIfNeeded();
    }

    @SuppressWarnings("deprecation")
    private void resolveNext(int run) {
        if (resolving || resolveQueue.isEmpty() || !active || run != discoveryGeneration) return;
        resolving = true;
        NsdServiceInfo next = resolveQueue.remove();
        try {
            nsd.resolveService(next, new NsdManager.ResolveListener() {
                @Override public void onResolveFailed(NsdServiceInfo service, int code) {
                    ui.post(() -> {
                        if (run != discoveryGeneration) return;
                        resolving = false;
                        if (code == NsdManager.FAILURE_ALREADY_ACTIVE) ui.postDelayed(() -> { resolveQueue.add(service); resolveNext(run); }, 300);
                        resolveNext(run);
                    });
                }
                @Override public void onServiceResolved(NsdServiceInfo service) {
                    ui.post(() -> {
                        if (run != discoveryGeneration) return;
                        resolving = false;
                        services.put(service.getServiceName(), service);
                        // Wechseln, wenn der gewählte Computer auftaucht, während das Handy mit einem anderen verbunden ist.
                        if (preferred != null && preferred.equals(service.getServiceName()) && current != null && !preferred.equals(current)) {
                            disconnect();
                        }
                        listener.changed();
                        connectIfNeeded();
                        resolveNext(run);
                    });
                }
            });
        } catch (RuntimeException e) {
            resolving = false;
        }
    }

    /** Wechselt zu einem anderen Computer und merkt sich die Wahl. */
    void choose(String name) {
        preferred = name;
        prefs.edit().putString("preferredDesktop", name).apply();
        if (!name.equals(current)) disconnect();
        connectIfNeeded();
        listener.changed();
    }

    /** Eine von Hand eingegebene Adresse (falls Bonjour im WLAN blockiert ist). */
    void manual(String host, int port) {
        String name = host + ":" + port;
        prefs.edit().putString("manualDesktop", name).apply();
        choose(name);
    }

    private void connectIfNeeded() {
        if (!active || connected || connecting) return;
        String target = null;
        if (preferred != null && (services.containsKey(preferred) || preferred.equals(manualAddress()))) target = preferred;
        if (target == null && !services.isEmpty()) target = services.keySet().iterator().next();
        if (target == null && manualAddress() != null) target = manualAddress();
        if (target == null) return;
        NsdServiceInfo info = services.get(target);
        if (info != null && info.getHost() != null) {
            connect(info.getHost().getHostAddress(), info.getPort(), target);
        } else if (info == null && target.contains(":")) {
            int colon = target.lastIndexOf(':');
            try {
                connect(target.substring(0, colon), Integer.parseInt(target.substring(colon + 1)), target);
            } catch (NumberFormatException ignored) {}
        }
    }

    private void connect(String address, int port, String name) {
        connecting = true;
        current = name;
        int run = generation;
        listener.changed();
        io.execute(() -> {
            Socket candidate = new Socket();
            try {
                candidate.connect(new InetSocketAddress(address, port), 5000);
                candidate.setTcpNoDelay(true);
                candidate.setKeepAlive(true);
                synchronized (this) {
                    if (!active || run != generation) { candidate.close(); return; }
                    socket = candidate;
                }
                ui.post(() -> {
                    if (run != generation) return;
                    connected = true;
                    connecting = false;
                    send(Json.obj("hello", deviceName()));
                    listener.changed();
                });
                InputStream input = candidate.getInputStream();
                PacketFramer framer = new PacketFramer();
                byte[] chunk = new byte[65536];
                int count;
                while ((count = input.read(chunk)) != -1) {
                    for (String line : framer.feed(chunk, count)) {
                        JSONObject packet = Json.parse(line);
                        if (packet != null) ui.post(() -> { if (run == generation) receive(packet); });
                    }
                }
            } catch (Exception ignored) {
            } finally {
                try { candidate.close(); } catch (Exception ignored) {}
                ui.post(() -> {
                    if (run != generation) return;
                    disconnect();
                    listener.changed();
                    ui.postDelayed(this::connectIfNeeded, 1500);
                });
            }
        });
    }

    private void receive(JSONObject packet) {
        String hello = Json.str(packet, "hello");
        if (hello != null) { desktopName = hello; listener.changed(); }
        JSONObject face = packet.optJSONObject("face");
        if (face != null) {
            listener.face(face.optDouble("gazeX", 0), face.optDouble("gazeY", 0),
                Mood.from(face.optString("mood", "listening")), face.optDouble("talk", 0));
        }
        String command = Json.str(packet, "command");
        if (command == null) return;
        String id = Json.str(packet, "callID");
        Consumer<JSONObject> done = id == null ? null : waiting.remove(id);
        if (done != null) done.accept(packet);
        else listener.command(command, packet);
    }

    void send(JSONObject packet) {
        Socket target = socket;
        if (target == null) return;
        writes.execute(() -> {
            try {
                byte[] data = (packet.toString() + "\n").getBytes(StandardCharsets.UTF_8);
                OutputStream out = target.getOutputStream();
                out.write(data);
                out.flush();
            } catch (Exception e) {
                try { target.close(); } catch (Exception ignored) {}
            }
        });
    }

    /** Schickt eine Anfrage an den Computer und ruft mit seiner Antwort zurück (null, wenn er weg ist). */
    void request(JSONObject packet, Consumer<JSONObject> done) {
        if (!connected || socket == null) { done.accept(null); return; }
        String id = UUID.randomUUID().toString();
        Json.put(packet, "callID", id);
        waiting.put(id, done);
        send(packet);
        String command = packet.optString("command");
        long timeout = command.equals("transcribe") ? 600_000 : command.equals("tool") ? 150_000 : 40_000;
        ui.postDelayed(() -> {
            Consumer<JSONObject> late = waiting.remove(id);
            if (late != null) late.accept(null);
        }, timeout);
    }

    private synchronized void disconnect() {
        generation++;
        connected = connecting = false;
        desktopName = null;
        Socket old = socket;
        socket = null;
        if (old != null) try { old.close(); } catch (Exception ignored) {}
        List<Consumer<JSONObject>> callbacks = new ArrayList<>(waiting.values());
        waiting.clear();
        for (Consumer<JSONObject> callback : callbacks) callback.accept(null);
    }

    void stop() {
        active = false;
        discoveryGeneration++;
        disconnect();
        if (discovery != null) try { nsd.stopServiceDiscovery(discovery); } catch (Exception ignored) {}
        discovery = null;
        resolving = false;
        resolveQueue.clear();
        services.clear();
        current = null;
        listener.changed();
    }

    void destroy() {
        stop();
        io.shutdownNow();
        writes.shutdownNow();
    }

    static String deviceName() {
        String model = Build.MODEL == null ? "Android" : Build.MODEL;
        String maker = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER;
        if (!maker.isEmpty() && !model.toLowerCase().startsWith(maker.toLowerCase())) model = maker + " " + model;
        return model;
    }
}
