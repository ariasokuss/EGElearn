const fs = require("fs");
const path = require("path");

const target = path.join(__dirname, "..", "src", "shared", "api", "generated", "api.ts");
let s = fs.readFileSync(target, "utf8");
const needle = "formData.append(`names`, bodyUploadDocumentsApiV1FilesFoldersFolderIdDocumentsBatchPost.names);";
const replacement =
  "bodyUploadDocumentsApiV1FilesFoldersFolderIdDocumentsBatchPost.names.forEach(value => formData.append(`names`, value));";
if (s.includes(needle)) {
  s = s.replace(needle, replacement);
  fs.writeFileSync(target, s);
  process.stdout.write("patched FormData names[] in documents batch upload\n");
}
