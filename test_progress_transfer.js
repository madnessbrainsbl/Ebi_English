const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const initSqlJs = require("./sql-wasm.js");

const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
assert(html.includes("<summary>Голос</summary>"), "voice summary not found");
assert(
  /<summary>(?:Данные прогресса|Прогресс)<\/summary>/.test(html),
  "progress tools summary not found",
);
const functionMatch = html.match(
  /function validateProgressDb\(db\) \{([\s\S]*?)\n      \}/,
);
assert(functionMatch, "validateProgressDb not found");
const validateProgressDb = new Function("db", functionMatch[1]);

const wasmBase64 = vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, "sql-wasm-b64.js"), "utf8") + ";SQL_WASM_B64",
);

async function main() {
  const SQL = await initSqlJs({
    wasmBinary: Buffer.from(wasmBase64, "base64"),
  });
  const source = new SQL.Database();
  source.run(`
    CREATE TABLE card_progress (
      card_id TEXT PRIMARY KEY,
      ease REAL, interval INTEGER, reps INTEGER, due INTEGER,
      correct INTEGER, wrong INTEGER, streak INTEGER
    );
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
  `);
  source.run("INSERT INTO card_progress VALUES (?,?,?,?,?,?,?,?)", [
    "test",
    2.5,
    1,
    2,
    0,
    3,
    1,
    2,
  ]);

  const imported = new SQL.Database(source.export());
  assert.doesNotThrow(() => validateProgressDb(imported));
  assert.equal(
    imported.exec("SELECT reps FROM card_progress")[0].values[0][0],
    2,
  );

  const invalid = new SQL.Database();
  assert.throws(() => validateProgressDb(invalid));

  invalid.close();
  imported.close();
  source.close();
  console.log("Progress export/import validation passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
