const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync(require("node:path").join(__dirname, "index.html"), "utf8");
assert(
  html.includes("ГРАММАТИКА — ВПИШИ АНГЛИЙСКИЕ СЛОВА В ПРОПУСК"),
  "grammar task must state that the answer is in English",
);
assert(
  /inp\.placeholder\s*=\s*"Напиши по-английски"/.test(
    html,
  ),
  "grammar input must state the expected language",
);
assert(
  html.includes('aiCheckBtn.textContent = "Объяснить ошибку с ИИ"'),
  "grammar mistakes must offer an optional AI explanation",
);
assert(
  html.includes('onclick="handleAiHelp()"'),
  "AI help button must route grammar explanations",
);

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} not found`);
  const bodyStart = html.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < html.length; index++) {
    if (html[index] === "{") depth++;
    if (html[index] === "}") depth--;
    if (depth === 0) return html.slice(start, index + 1);
  }
  throw new Error(`${name} is incomplete`);
}

const context = {
  VOCAB: {
    COLORS: { grammar: false },
    GRAMMAR: { grammar: true },
  },
  Math,
};
vm.createContext(context);
vm.runInContext(
  ["buildMatchPool", "finalizeQueue", "expandTheoryPractice"]
    .map(extractFunction)
    .join("\n"),
  context,
);

const colors = Array.from({ length: 6 }, (_, index) => ({
  id: `COLORS_${index}`,
  lvl: "COLORS",
  card: { en: `color-${index}`, ru: `цвет-${index}` },
}));
const unrelated = {
  id: "COLORS_unrelated",
  lvl: "COLORS",
  card: { en: "unrelated", ru: "постороннее" },
};
const grammar = Array.from({ length: 6 }, (_, index) => ({
  id: `GRAMMAR_${index}`,
  lvl: "GRAMMAR",
  card: { en: `rule-${index}`, ru: `правило-${index}` },
}));
context.VOCAB.GRAMMAR.cards = grammar.map((item) => item.card);
const expandedPractice = context.expandTheoryPractice([colors[0], grammar[0]], [
  "GRAMMAR",
]);
assert.equal(
  expandedPractice.filter((item) => item.lvl === "GRAMMAR").length,
  grammar.length,
  "new grammar theory must be followed by its complete practice set",
);

const scopedQueue = context.finalizeQueue(colors.map((item) => ({ ...item })));
const matchStep = scopedQueue.find((item) => item.mode === "match");
assert(matchStep, "six vocabulary cards must create a matching round");
assert.deepEqual(
  Array.from(matchStep.cards, (card) => card.en),
  colors.map((item) => item.card.en),
  "matching round must use only cards from the current lesson queue",
);
assert(!matchStep.cards.includes(unrelated.card));

const grammarQueue = context.finalizeQueue(grammar.map((item) => ({ ...item })));
assert.equal(
  grammarQueue.some((item) => item.mode === "match"),
  false,
  "grammar practice must not be interrupted by unrelated matching cards",
);

vm.runInContext(
  ["requiredStreak", "isLearned", "scheduleCardRepeat", "grammarCue"]
    .map(extractFunction)
    .join("\n"),
  context,
);
assert.equal(
  context.grammarCue({ ru: "You", tip: "Ты/Вы = You" }),
  "Ты/Вы",
  "ambiguous grammar blanks must show a meaning cue",
);
context.queue = [{ id: "COLORS_red", lvl: "COLORS", card: colors[0].card }];
context.qIdx = 0;
const progress = { reps: 1, wrong: 4, streak: 1 };
assert.equal(context.isLearned(progress), false);
context.scheduleCardRepeat(context.queue[0]);
assert.equal(context.queue.length, 2, "an unmastered card must be queued again");
progress.streak = 3;
assert.equal(context.isLearned(progress), true);

console.log("Session scope and mastery repetition validation passed");

const numMap = html.match(/const NUM_MAP = \{[\s\S]*?\n      \};/);
assert(numMap, "NUM_MAP missing");
const answerContext = { Math };
vm.createContext(answerContext);
vm.runInContext(
  [
    numMap[0],
    ...["norm", "stripArticle", "lev", "canon", "isCorrect", "isClose", "parseTrackLines"].map(
      extractFunction,
    ),
  ].join("\n"),
  answerContext,
);
assert.equal(answerContext.isCorrect("were", "where"), false);
assert.equal(answerContext.isCorrect("effect", "affect"), false);
assert.equal(answerContext.isCorrect("мои", "мой"), false);
assert.equal(answerContext.isCorrect("an apple", "apple"), true);
assert.equal(answerContext.isCorrect("thanks", "thank you"), true);
assert.equal(answerContext.isCorrect("5", "five"), true);
assert.equal(answerContext.isCorrect("applle", "apple", true), true);
assert.equal(answerContext.isClose("applle", "apple"), true);
const chapters = answerContext.parseTrackLines(
  "Latency - Задержка - High - latency stays\n\nThroughput - Пропускная способность - Fast.",
);
assert.equal(chapters.length, 2);
assert.equal(chapters[0][0].ex, "High - latency stays");
assert.equal(chapters[1][0].ru, "Пропускная способность");
console.log("Answer checking and custom-track parsing passed");
