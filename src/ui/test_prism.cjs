const Prism = require('prismjs');
require('prismjs/components/prism-yaml');
require('prismjs/components/prism-markdown');
console.log(Prism.languages.yaml ? "yaml ok" : "yaml missing");
console.log(Prism.languages.markdown ? "markdown ok" : "markdown missing");
try {
  Prism.highlight("# hello", Prism.languages.markdown, "markdown");
  console.log("markdown highlight ok");
} catch(e) {
  console.error("markdown highlight error:", e);
}
try {
  Prism.highlight("foo: bar", Prism.languages.yaml, "yaml");
  console.log("yaml highlight ok");
} catch(e) {
  console.error("yaml highlight error:", e);
}
