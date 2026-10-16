package io.github.anonym239.bluey;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Einstellungen des Handys und sein eigener OpenAI-Schlüssel (nur für den Modus ohne PC).
 * Gespeichert wird nur der verschlüsselte Schlüssel; der Schlüssel dafür bleibt im Android Keystore.
 */
final class PhoneCredentials {
    private static final String ALIAS = "Bluey.OpenAI.v1";
    private final SharedPreferences prefs;

    PhoneCredentials(Context context) { prefs = context.getSharedPreferences("bluey_voice", Context.MODE_PRIVATE); }

    /** Ohne PC: das Handy spricht direkt mit OpenAI. Standard ist (wie beim iPhone) der PC. */
    boolean phoneMode() { return prefs.getBoolean("phone_mode", false); }
    /** Antworten zusätzlich mit der Android-Stimme vorlesen. */
    boolean spokenReplies() { return prefs.getBoolean("spoken_replies", false); }
    void configure(boolean phone, boolean spoken) {
        prefs.edit().putBoolean("phone_mode", phone).putBoolean("spoken_replies", spoken).apply();
    }

    double volume() { return prefs.getFloat("volume", 1f); }
    void setVolume(double volume) { prefs.edit().putFloat("volume", (float) volume).apply(); }

    boolean hasKey() { return !prefs.getString("key_ciphertext", "").isEmpty(); }

    private SecretKey wrappingKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return ((KeyStore.SecretKeyEntry) store.getEntry(ALIAS, null)).getSecretKey();
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    void save(String key) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey());
        byte[] encrypted = cipher.doFinal(key.trim().getBytes(StandardCharsets.UTF_8));
        if (!prefs.edit().putString("key_ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP))
                .putString("key_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit())
            throw new java.io.IOException("Schlüssel konnte nicht gespeichert werden");
    }

    /** Der gespeicherte Schlüssel, oder "" wenn keiner da ist. */
    String read() throws Exception {
        String encrypted = prefs.getString("key_ciphertext", "");
        if (encrypted.isEmpty()) return "";
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, wrappingKey(),
            new GCMParameterSpec(128, Base64.decode(prefs.getString("key_iv", ""), Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }

    String readOrEmpty() {
        try { return read(); } catch (Exception e) { return ""; }
    }

    void remove() { prefs.edit().remove("key_ciphertext").remove("key_iv").apply(); }
}
