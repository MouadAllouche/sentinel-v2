import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import prettier from "eslint-config-prettier";
import jsxA11y from "eslint-plugin-jsx-a11y";

const config = [
  { ignores: [".next/**", "node_modules/**", "lib/api/schema.d.ts", "next-env.d.ts", "coverage/**"] },
  ...nextCoreWebVitals,
  {
    // eslint-config-next already registers the jsx-a11y plugin.
    rules: jsxA11y.configs.recommended.rules,
  },
  prettier,
];

export default config;
