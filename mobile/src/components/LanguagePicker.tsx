import { Pressable, StyleSheet, Text, View } from "react-native";

import { locales } from "../i18n";
import { useI18n } from "../i18n/I18nProvider";

export function LanguagePicker() {
  const { locale, setLocale, t } = useI18n();

  return (
    <View style={styles.row} accessibilityRole="radiogroup" accessibilityLabel={t("language")}>
      {locales.map(({ code, label }) => (
        <Pressable
          key={code}
          onPress={() => setLocale(code)}
          hitSlop={10}
          accessibilityRole="radio"
          accessibilityLabel={label}
          accessibilityState={{ selected: locale === code }}
          style={[styles.chip, locale === code && styles.chipActive]}
        >
          <Text style={[styles.chipLabel, locale === code && styles.chipLabelActive]}>
            {code.toUpperCase()}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 6, alignSelf: "flex-end" },
  chip: {
    borderRadius: 999,
    minHeight: 32,
    minWidth: 40,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  chipActive: { backgroundColor: "#27272a" },
  chipLabel: { color: "#a1a1aa", fontSize: 13 },
  chipLabelActive: { color: "#fff" },
});
