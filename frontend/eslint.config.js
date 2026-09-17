import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.ts", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  // Typed rules need a project, and the config file itself is not in one.
  { files: ["**/*.js"], ...tseslint.configs.disableTypeChecked },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: { project: ["./tsconfig.app.json", "./tsconfig.node.json"], tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
);
