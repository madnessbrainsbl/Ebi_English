const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('./browser_support');

const results = [];
const root = path.resolve(__dirname, '..');
const artifactDir = path.join(root, 'dev', 'audit-artifacts');
fs.mkdirSync(artifactDir, { recursive: true });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  async function test(name, fn) {
    try { await fn(); results.push({ name, passed: true }); console.log('PASS', name); }
    catch (error) { results.push({ name, passed: false, error: error.message }); console.log('FAIL', name, error.message); }
  }
  async function open(init) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    const appUrl = process.env.AUDIT_URL || pathToFileURL(path.join(root, 'index.html')).href;
    const origin = new URL(appUrl).origin;
    await context.route(/^https?:/, route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    if (init) await page.addInitScript(init);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(appUrl);
    await page.waitForFunction(() => document.querySelectorAll('.level-block').length === 7);
    await page.evaluate(() => { speak = () => {}; prefetchSpeak = () => {}; });
    return { context, page, errors };
  }
  const { page, context, errors } = await open();
  await test('initial content and screens', async () => {
    assert.equal(await page.evaluate(() => Object.keys(VOCAB).length), 300);
    for (const screen of ['mycards', 'stats', 'freechat', 'home']) {
      await page.evaluate(screen => showScreen(screen), screen);
      assert(await page.locator('#screen-' + screen).isVisible());
    }
  });
  await test('no bundled AI credential', async () => assert(await page.evaluate(() => DEFAULT_AI_KEY === ''), 'AI default key must be empty'));
  await test('Markdown removes executable HTML', async () => {
    const html = await page.evaluate(() => renderMarkdownContent('<img src=x onerror="window.auditXss=1"><svg onload="window.auditXss=2"></svg>[bad](javascript:alert%281%29) **safe**'));
    assert(!/onerror|onload|javascript:|<svg/i.test(html));
    assert(html.includes('<strong>safe</strong>'));
  });
  await test('cached translations are escaped', async () => {
    const html = await page.evaluate(() => buildBotMsgElement('Hello', { translation: '<img onerror="alert(1)">' }).innerHTML);
    assert(!html.includes('<img onerror'));
  });
  await test('stored collection nulls do not crash', async () => {
    const valid = await page.evaluate(() => {
      for (const key of ['eng_mycards', 'eng_custom_books', 'custom_science_tracks', 'eng_trans']) localStorage.setItem(key, 'null');
      return Array.isArray(loadMyCards()) && Array.isArray(loadCustomBooks()) && !!getCustomTracks() && !!loadTransCache();
    });
    await page.evaluate(() => ['eng_mycards', 'eng_custom_books', 'custom_science_tracks', 'eng_trans'].forEach(k => localStorage.removeItem(k)));
    assert(valid);
  });
  await test('untranslated custom track does not create placeholder cards', async () => {
    const before = await page.evaluate(() => JSON.stringify(getCustomTracks()));
    await page.evaluate(() => {
      document.getElementById('custom-track-title-input').value = 'Audit track';
      document.getElementById('custom-track-words-input').value = '';
      saveCustomTrackFromForm();
    });
    assert.equal(await page.evaluate(() => JSON.stringify(getCustomTracks())), before);
  });
  await test('grammar requires exact articles and verb forms', async () => {
    const correct = await page.evaluate(() => {
      VOCAB.AUDIT_GRAMMAR = { grammar: true, cards: [{ en: 'I see ___ car.', ru: 'a car' }] };
      beginSession([{ id: 'AUDIT_GRAMMAR_test', lvl: 'AUDIT_GRAMMAR', card: VOCAB.AUDIT_GRAMMAR.cards[0] }], 1, []);
      document.getElementById('answer-input').value = 'the car';
      checkAnswer();
      return sessStats.correct;
    });
    assert.equal(correct, 0);
  });
  await test('leaving session cancels automatic advance', async () => {
    const state = await page.evaluate(() => {
      const card = VOCAB['1'].cards[0];
      beginSession([{ id: '1_' + card.en, lvl: '1', card }, { id: '1_' + VOCAB['1'].cards[1].en, lvl: '1', card: VOCAB['1'].cards[1] }], 0, []);
      document.getElementById('answer-input').value = card.en.split('/')[0];
      checkAnswer(); showScreen('home');
      return { index: qIdx, sessions: P.sessions };
    });
    await delay(1350);
    assert.deepEqual(await page.evaluate(() => ({ index: qIdx, sessions: P.sessions })), state);
    assert(await page.locator('#screen-home').isVisible());
  });
  await test('matching delay does not change a later session', async () => {
    await page.evaluate(() => {
      beginSession([{ mode: 'match', cards: VOCAB['1'].cards.slice(0, 6) }], 0, []);
      for (const button of [...document.querySelectorAll('#sess-match-col-en .match-tile')]) {
        button.click();
        const idx = matchSelectedEn?.idx;
        const ru = [...document.querySelectorAll('#sess-match-col-ru .match-tile')].find(b => b.textContent === matchCards[idx]?.ru.split('/')[0].trim());
        ru?.click();
      }
      startLevelSession('1');
    });
    await delay(750);
    assert.equal(await page.evaluate(() => qIdx), 0);
  });
  await test('AI request reset does not resurrect an old chat', async () => {
    await page.evaluate(() => {
      resetChat(); showScreen('freechat');
      window.auditOldFetch = fetchAiChat;
      fetchAiChat = () => new Promise(resolve => window.auditResolve = resolve);
      document.getElementById('chat-input').value = 'Old chat';
      window.auditChatPromise = sendChatMessage();
      resetChat();
      window.auditResolve({ choices: [{ message: { content: 'Late response' } }] });
    });
    await page.evaluate(() => window.auditChatPromise);
    const historyLength = await page.evaluate(() => chatHistory.length);
    const text = await page.locator('#chat-messages').textContent();
    await page.evaluate(() => { fetchAiChat = window.auditOldFetch; });
    assert.equal(historyLength, 0);
    assert.equal(text, '');
  });
  await test('AI accepts a regular JSON response when streaming was requested', async () => {
    assert.equal(await page.evaluate(async () => {
      const old = window.fetch;
      window.fetch = async () => new Response(JSON.stringify({ choices: [{ message: { content: 'JSON answer' } }] }), { headers: { 'Content-Type': 'application/json' } });
      try { return await streamAiChat([{ role: 'user', content: 'test' }]); }
      finally { window.fetch = old; }
    }), 'JSON answer');
  });
  await test('custom endpoint authentication errors do not send keys to other endpoints', async () => {
    const urls = await page.evaluate(async () => {
      const old = window.fetch; const oldUrl = localStorage.getItem(AI_URL_LS);
      saveAiUrl('https://audit.invalid/v1/chat/completions');
      const calls = [];
      window.fetch = async url => { calls.push(url); return new Response('{}', { status: 401 }); };
      try { await fetchAiChat([]); } catch {}
      finally { window.fetch = old; if (oldUrl) localStorage.setItem(AI_URL_LS, oldUrl); else localStorage.removeItem(AI_URL_LS); }
      return calls;
    });
    assert.deepEqual(urls, ['https://audit.invalid/v1/chat/completions']);
  });
  await test('quota failure during card creation is handled', async () => {
    const outcome = await page.evaluate(() => {
      const old = Storage.prototype.setItem;
      Storage.prototype.setItem = () => { throw new DOMException('Quota full', 'QuotaExceededError'); };
      try { return addMyCard('audit quota', 'тест', '') === false; }
      finally { Storage.prototype.setItem = old; }
    });
    assert(outcome);
  });
  await test('all home lessons are operable with a keyboard', async () => {
    await page.evaluate(() => showScreen('home'));
    assert.equal(await page.locator('#levels-grid .level-row.trainable:not([tabindex="0"]):not(button)').count(), 0);
    assert.equal(await page.locator('.level-block-header:not([tabindex="0"]):not(button)').count(), 0);
  });
  await test('mobile screens and modals do not overflow', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const screen of ['home', 'mycards', 'stats', 'freechat']) {
      await page.evaluate(screen => showScreen(screen), screen);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), screen);
    }
    for (const [openFn, closeFn] of [['openAiModal', 'closeAiModal'], ['openGroqModal', 'closeGroqModal'], ['openDeepgramModal', 'closeDeepgramModal'], ['openScienceTracksModal', 'closeScienceTracksModal']]) {
      await page.evaluate(fn => window[fn](), openFn);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), openFn);
      await page.evaluate(fn => window[fn](), closeFn);
    }
    await page.evaluate(() => showScreen('home'));
    await page.screenshot({ path: path.join(artifactDir, 'mobile.png') });
  });
  await test('browser reports no unexpected JavaScript exceptions', async () => assert.deepEqual(errors, []));
  await test('manual card create, search, duplicate and delete', async () => {
    await page.evaluate(() => { showScreen('mycards'); });
    await page.locator('#add-src').fill('audit phrase');
    await page.locator('#add-dst').fill('проверочная фраза');
    await page.locator('#add-ex').fill('An audit phrase.');
    await page.locator('button[onclick="saveMyCard()"]').click();
    await page.locator('#tab-saved').click();
    assert.equal(await page.locator('.my-card-row').count(), 1);
    await page.locator('#search-my-cards').fill('not present');
    assert.equal(await page.locator('.my-card-row').count(), 0);
    await page.locator('#search-my-cards').fill('audit');
    assert.equal(await page.locator('.my-card-row').count(), 1);
    assert.equal(await page.evaluate(() => addMyCard('audit phrase', 'duplicate', '')), false);
    await page.locator('.my-card-del').click();
    assert.equal(await page.locator('.my-card-row').count(), 0);
  });
  await test('all settings modals close with Escape', async () => {
    for (const [fn, selector] of [['openAiModal', '#ai-modal'], ['openGroqModal', '#groq-modal'], ['openDeepgramModal', '#deepgram-modal'], ['openScienceTracksModal', '#science-tracks-modal'], ['openTacticsModal', '#tactics-modal']]) {
      await page.evaluate(fn => window[fn](), fn);
      assert(await page.locator(selector).isVisible());
      await page.keyboard.press('Escape');
      assert(!(await page.locator(selector).isVisible()));
    }
  });
  await test('edit science badge opens the editor', async () => {
    await page.evaluate(() => showScreen('home'));
    await page.locator('.science-edit-badge').first().click();
    assert(await page.locator('#science-tracks-modal').isVisible());
    await page.keyboard.press('Escape');
  });
  await test('modal keyboard focus stays inside and returns after close', async () => {
    await page.evaluate(() => showScreen('home'));
    await page.locator('#ai-settings-details > summary').click();
    await page.locator('#ai-btn').click();
    await page.waitForFunction(() => activeModal?.id === 'ai-modal');
    const focusable = page.locator('#ai-modal button:visible, #ai-modal input:visible, #ai-modal select:visible');
    await focusable.last().focus();
    await page.keyboard.press('Tab');
    assert(await page.evaluate(() => document.getElementById('ai-modal').contains(document.activeElement)));
    assert(await page.evaluate(() => document.getElementById('screen-home').inert));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !activeModal);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'ai-btn');
  });
  await test('strict grammar preserves apostrophes and valid words are not typos', async () => {
    assert.deepEqual(await page.evaluate(() => [isCorrect('cant', "can't", false, true), isCorrect('can’t', "can't", false, true), isCorrect('effect', 'affect', true), isCorrect('', '/')]), [false, true, false, false]);
  });
  await test('custom track chapter count and card data are preserved', async () => {
    await page.evaluate(() => {
      document.getElementById('custom-track-title-input').value = 'Audit chapters';
      document.getElementById('custom-track-words-input').value = 'Latency - Задержка - High - latency\n\nThroughput - Пропускная способность';
      document.getElementById('custom-track-slot-select').value = '2';
      saveCustomTrackFromForm();
    });
    const track = await page.evaluate(() => getCustomTracks()[getActiveTracks()[2].id]);
    assert.equal(track.chapters.length, 2);
    assert.equal(track.chapters[0].cards[0].ex, 'High - latency');
    await page.evaluate(() => { closeScienceTracksModal(); startScienceSeries(getActiveTracks()[2].id); });
    assert.equal(await page.evaluate(() => queue[0].card.en), 'Latency');
  });
  await test('track edits roll back when storing active slots fails', async () => {
    const unchanged = await page.evaluate(() => {
      const old = Storage.prototype.setItem;
      const before = localStorage.getItem('custom_science_tracks');
      document.getElementById('custom-track-title-input').value = 'Edited audit track';
      document.getElementById('custom-track-words-input').value = 'Changed - Изменено';
      Storage.prototype.setItem = function(key, value) { if (key === 'active_science_tracks') throw new DOMException('Quota', 'QuotaExceededError'); return old.call(this, key, value); };
      try { saveCustomTrackFromForm(); return localStorage.getItem('custom_science_tracks') === before; }
      finally { Storage.prototype.setItem = old; closeScienceTracksModal(); }
    });
    assert(unchanged);
  });
  await test('complete vocabulary lesson persists progress once', async () => {
    const before = await page.evaluate(() => { showScreen('home'); return P.sessions; });
    await page.evaluate(() => { startLevelSession('1'); });
    let count = 0;
    while (await page.locator('#screen-session').isVisible() && count++ < 100) {
      const match = await page.evaluate(() => queue[qIdx]?.mode === 'match');
      if (match) {
        await page.evaluate(() => {
          const en = [...document.querySelectorAll('#sess-match-col-en .match-tile')];
          const ru = [...document.querySelectorAll('#sess-match-col-ru .match-tile')];
          for (const button of en) {
            button.click();
            const idx = matchSelectedEn?.idx;
            ru.find(b => b.textContent === matchCards[idx]?.ru.split('/')[0].trim())?.click();
          }
        });
        await page.waitForFunction(() => queue[qIdx]?.mode !== 'match');
      } else {
        const answer = await page.evaluate(() => getEnglishText(queue[qIdx].card, VOCAB[queue[qIdx].lvl]?.grammar));
        await page.locator('#answer-input').fill(answer);
        await page.locator('#answer-input').press('Enter');
        await page.locator('#next-btn').click();
      }
    }
    assert(await page.locator('#screen-result').isVisible());
    assert.equal(await page.evaluate(() => P.sessions), before + 1);
    await page.evaluate(() => endSession());
    assert.equal(await page.evaluate(() => P.sessions), before + 1);
    assert((await page.evaluate(() => P.correct)) > 0);
  });
  await test('SQLite export imports identical progress and preserves unrelated storage', async () => {
    await page.evaluate(() => showScreen('home'));
    const downloading = page.waitForEvent('download');
    await page.evaluate(() => exportProgress());
    const download = await downloading;
    assert.equal(download.suggestedFilename(), 'english-progress.sqlite');
    const file = path.join(artifactDir, 'synthetic-progress.sqlite');
    await download.saveAs(file);
    const before = await page.evaluate(() => JSON.stringify(P));
    await page.evaluate(() => { localStorage.setItem('audit-unrelated', 'preserved'); P.correct = 0; save(); });
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#progress-file').setInputFiles(file);
    await page.waitForFunction(expected => typeof P !== 'undefined' && document.querySelectorAll('.level-block').length === 7 && JSON.stringify(P) === expected, before);
    assert.equal(await page.evaluate(() => localStorage.getItem('audit-unrelated')), 'preserved');
    await page.evaluate(() => { speak = () => {}; prefetchSpeak = () => {}; });
  });
  await test('native PDF and DOCX imports work when opened as a file', async () => {
    const fixtures = path.join(__dirname, 'audit-fixtures');
    for (const name of ['sample.pdf', 'sample.docx']) {
      if (!fs.existsSync(path.join(fixtures, name))) throw new Error('Run python dev/make_audit_fixtures.py first');
      await page.evaluate(() => { showScreen('mycards'); switchTab('reading'); });
      await page.locator('#book-file-input').setInputFiles(path.join(fixtures, name));
      await page.waitForFunction(() => loadCustomBooks().some(book => book.title === 'sample'));
      const book = await page.evaluate(() => loadCustomBooks().find(book => book.title === 'sample'));
      assert(book.pages.join(' ').includes('Hello audit'));
      await page.evaluate(id => { const books = loadCustomBooks().filter(book => book.id !== id); saveCustomBooks(books); }, book.id);
    }
  });
  await test('TXT pagination and keyboard navigation', async () => {
    await page.evaluate(() => { showScreen('mycards'); switchTab('reading'); });
    await page.locator('#book-file-input').setInputFiles({ name: 'audit.txt', mimeType: 'text/plain', buffer: Buffer.from(Array.from({ length: 400 }, () => 'hello').join(' ')) });
    await page.waitForFunction(() => loadCustomBooks().some(book => book.title === 'audit'));
    await page.locator('#reading-grid .level-row').first().click();
    await page.locator('#reading-title').click();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#reading-page-indicator').textContent(), '2 / 3');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.locator('#reading-page-indicator').textContent(), '1 / 3');
  });
  await test('SSE DONE finishes without waiting for server connection to close', async () => {
    const reply = await page.evaluate(async () => {
      const old = window.fetch;
      window.fetch = async () => new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('data: {"choices":[{"delta":{"content":"Finished"}}]}\n\ndata: [DONE]\n\n')); } }), { headers: { 'Content-Type': 'text/event-stream' } });
      try { return await streamAiChat([], null, 100); } finally { window.fetch = old; }
    });
    assert.equal(reply, 'Finished');
  });
  await test('connection check verifies selected model, not only model listing', async () => {
    const result = await page.evaluate(async () => {
      const old = window.fetch; const calls = [];
      window.fetch = async (url, options) => { calls.push({ url, method: options.method }); return new Response('{}', { status: options.method === 'POST' ? 404 : 200 }); };
      try { return { result: await verifyAiConnection('http://127.0.0.1:8080/v1/chat/completions', '', 'missing-model'), calls }; }
      finally { window.fetch = old; }
    });
    assert.equal(result.result.ok, false);
    assert.equal(result.calls[0].method, 'POST');
  });
  await test('SQLite sync rolls back on write failure', async () => {
    const unchanged = await page.evaluate(() => {
      const before = bytesToBase64(progressDB.export());
      const prepare = progressDB.prepare;
      progressDB.prepare = () => { throw new Error('Synthetic SQLite failure'); };
      let success;
      try { success = syncProgressToDb(); } finally { progressDB.prepare = prepare; }
      return success === false && before === bytesToBase64(progressDB.export());
    });
    assert(unchanged);
  });
  await test('late pronunciation permission releases microphone without recording', async () => {
    const stopped = await page.evaluate(async () => {
      localStorage.setItem(AAI_KEY_LS, 'synthetic-audit-key');
      startLevelSession('1');
      const old = navigator.mediaDevices.getUserMedia;
      let resolve; let stopped = false;
      navigator.mediaDevices.getUserMedia = () => new Promise(r => resolve = r);
      const pending = togglePronCheck();
      showScreen('home');
      resolve({ getTracks: () => [{ stop: () => { stopped = true; } }] });
      try { await pending; return stopped && !pronRecording; }
      finally { navigator.mediaDevices.getUserMedia = old; localStorage.removeItem(AAI_KEY_LS); }
    });
    assert(stopped);
  });
  await test('late chat microphone permission is discarded after reset', async () => {
    const stopped = await page.evaluate(async () => {
      saveGroqKey('synthetic-audit-key'); showScreen('freechat');
      const old = navigator.mediaDevices.getUserMedia;
      let resolve; let stopped = false;
      navigator.mediaDevices.getUserMedia = () => new Promise(r => resolve = r);
      const pending = startChatVoiceInput('chat-input', sendChatMessage, 'en', 'chat-mic-btn');
      resetChat();
      resolve({ getTracks: () => [{ stop: () => { stopped = true; } }] });
      try { await pending; return stopped; }
      finally { navigator.mediaDevices.getUserMedia = old; localStorage.removeItem(GROQ_KEY_LS); }
    });
    assert(stopped);
  });
  await test('late sentence analysis cannot overwrite a newer card', async () => {
    const text = await page.evaluate(async () => {
      const old = fetchAiChat;
      let resolve;
      fetchAiChat = () => new Promise(r => resolve = r);
      pendingParseSentence = 'A unique audit sentence.';
      const promise = parseSentence();
      startLevelSession('1');
      document.getElementById('parse-body').textContent = 'New card';
      resolve({ choices: [{ message: { content: 'Old analysis' } }] });
      try { await promise; return document.getElementById('parse-body').textContent; }
      finally { fetchAiChat = old; }
    });
    assert.equal(text, 'New card');
  });
  await test('late semantic AI verdict cannot alter another session', async () => {
    const state = await page.evaluate(async () => {
      const old = fetchAiChat; let resolve;
      fetchAiChat = () => new Promise(r => resolve = r);
      const card = VOCAB['1'].cards[0];
      beginSession([{ id: '1_' + card.en, lvl: '1', mode: 'translate', card }], 0, []);
      dictationActive = false;
      document.getElementById('answer-input').value = 'audit wrong answer';
      checkAnswer();
      const pending = checkWithAi();
      startLevelSession('1');
      const before = JSON.stringify({ stats: sessStats, index: qIdx, correct: P.correct });
      resolve({ choices: [{ message: { content: 'ДА — acceptable' } }] });
      try { await pending; return before === JSON.stringify({ stats: sessStats, index: qIdx, correct: P.correct }); }
      finally { fetchAiChat = old; }
    });
    assert(state);
  });
  await test('storage quota failure does not discard a successful AI explanation', async () => {
    const answer = await page.evaluate(async () => {
      const oldFetch = fetchAiChat;
      const oldStore = Storage.prototype.setItem;
      fetchAiChat = async () => ({ choices: [{ message: { content: 'Successful explanation' } }] });
      Storage.prototype.setItem = () => { throw new DOMException('Quota', 'QuotaExceededError'); };
      try { await explainMistakeWithAi('1', false, 'audit prompt', 'correct', 'wrong'); return document.getElementById('ai-explain-body').textContent; }
      finally { fetchAiChat = oldFetch; Storage.prototype.setItem = oldStore; }
    });
    assert.equal(answer, 'Successful explanation');
  });
  await test('network helper times out while reading stalled response body', async () => {
    const aborted = await page.evaluate(async () => {
      const old = window.fetch;
      window.fetch = async (_, options) => ({ arrayBuffer: () => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Timed out', 'AbortError')))) });
      try { await fetchWithTimeout('https://audit.invalid', {}, 10); return false; }
      catch (e) { return e.name === 'AbortError'; }
      finally { window.fetch = old; }
    });
    assert(aborted);
  });
  await test('desktop session screenshot and no final browser exceptions', async () => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: path.join(artifactDir, 'desktop-session.png') });
    assert.deepEqual(errors, []);
  });
  await test('layout remains within 320, 360, 768 and 1280 pixel viewports', async () => {
    for (const width of [320, 360, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const screen of ['home', 'mycards', 'stats', 'freechat']) {
        await page.evaluate(screen => showScreen(screen), screen);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${width}: ${screen}`);
      }
    }
  });
  await context.close();
  await test('corrupt progress is preserved for recovery', async () => {
    const fixture = await open(() => localStorage.setItem('eng_progress_db', 'broken-progress-sample'));
    const preserved = await fixture.page.evaluate(() => localStorage.getItem('eng_progress_db') === 'broken-progress-sample' || localStorage.getItem('eng_progress_db_recovery') === 'broken-progress-sample');
    await fixture.context.close(); assert(preserved);
  });
  await test('invalid meta and negative counters in SQLite are rejected', async () => {
    const fixture = await open();
    const accepted = await fixture.page.evaluate(() => {
      const db = new SQLRuntime.Database();
      db.run('CREATE TABLE card_progress(card_id TEXT PRIMARY KEY,ease REAL,interval INTEGER,reps INTEGER,due INTEGER,correct INTEGER,wrong INTEGER,streak INTEGER); CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');
      db.run("INSERT INTO card_progress VALUES ('test',2.5,1,0,0,-10,0,0); INSERT INTO meta VALUES ('unlocked','null')");
      try { validateProgressDb(db); return true; } catch { return false; } finally { db.close(); }
    });
    await fixture.context.close(); assert.equal(accepted, false);
  });
  await test('legacy progress migration survives persistence quota failure', async () => {
    const fixture = await open(() => {
      localStorage.setItem('eng_v3', JSON.stringify({ cards: { test: { ease: 2.5, interval: 1, reps: 1, due: 0, correct: 4, wrong: 1 } }, unlocked: ['1'], sessions: 2, correct: 4, wrong: 1, log: [] }));
      const old = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) { if (key === 'eng_progress_db') throw new DOMException('Quota', 'QuotaExceededError'); return old.call(this, key, value); };
    });
    const state = await fixture.page.evaluate(() => ({ correct: P.correct, legacy: !!localStorage.getItem('eng_v3'), streak: P.cards.test.streak }));
    await fixture.context.close();
    assert.deepEqual(state, { correct: 4, legacy: true, streak: 1 });
  });
  await test('progress reset preserves keys, books and custom cards', async () => {
    const fixture = await open();
    await fixture.page.evaluate(() => { P.correct = 10; save(); localStorage.setItem('eng_groq_key', 'off'); addMyCard('audit retained', 'сохранено', ''); saveCustomBooks([{ id: 'retained', title: 'Retained', pages: ['Test'], curPage: 0 }]); });
    fixture.page.once('dialog', dialog => dialog.accept());
    await fixture.page.evaluate(() => clearProgress());
    await fixture.page.waitForFunction(() => typeof P !== 'undefined' && document.querySelectorAll('.level-block').length === 7 && P.correct === 0);
    assert.deepEqual(await fixture.page.evaluate(() => [loadMyCards().length, loadCustomBooks().length, localStorage.getItem('eng_groq_key')]), [1, 1, 'off']);
    await fixture.context.close();
  });
  await test('another tab cannot silently overwrite changed progress', async () => {
    const fixture = await open();
    const protectedStorage = await fixture.page.evaluate(() => { localStorage.setItem(PROGRESS_DB_KEY, 'other-tab-marker'); P.correct = 10; save(); return progressPersistenceBlocked && localStorage.getItem(PROGRESS_DB_KEY) === 'other-tab-marker'; });
    await fixture.context.close(); assert(protectedStorage);
  });
  await browser.close();
  const report = { date: '2026-10-04', origin: process.env.AUDIT_URL || 'file://', browser: browser.version(), passed: results.filter(r => r.passed).length, failed: results.filter(r => !r.passed).length, results };
  fs.writeFileSync(path.join(artifactDir, process.env.AUDIT_RESULT || 'regression-results.json'), JSON.stringify(report, null, 2));
  console.log(`${report.passed} passed; ${report.failed} failed`);
  process.exitCode = report.failed ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
