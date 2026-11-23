// In-page text dialog instead of window.prompt(), and guarded localStorage (T13).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../modules/gallery/__init__.py'), 'utf8');
const body = source.slice(source.indexOf("GALLERY_BODY = r'''"), source.indexOf("'''", source.indexOf("GALLERY_BODY = r'''") + 20));
const script = body.slice(body.indexOf('<script>'));

function functionSource(name) {
    const match = new RegExp('^(?:async )?function ' + name + '\\(', 'm').exec(source);
    assert.ok(match, name);
    let depth = 0;
    for (let i = source.indexOf('{', match.index); i < source.length; i++) {
        if (source[i] === '{') depth++;
        else if (source[i] === '}' && --depth === 0) return source.slice(match.index, i + 1);
    }
    throw Error(name);
}

function dialog() {
    const elements = {};
    const element = id => elements[id] || (elements[id] = {
        id, textContent: '', value: '', focused: false, selected: false,
        classList: {set: new Set(), add(c) { this.set.add(c); }, remove(c) { this.set.delete(c); }, contains(c) { return this.set.has(c); }},
        focus() { this.focused = true; }, select() { this.selected = true; },
    });
    const context = {textPromptResolve: null, Promise, setTimeout: fn => fn(), document: {getElementById: element}};
    vm.createContext(context);
    vm.runInContext(functionSource('askText') + '\n' + functionSource('finishTextPrompt'), context);
    return {context, element};
}

test('askText shows the dialog and resolves with the entered text', async () => {
    const {context, element} = dialog();
    const answer = context.askText('New collection', 'Name', 'Draft', 'Create');
    assert.equal(element('textPromptOverlay').classList.contains('open'), true);
    assert.equal(element('textPromptTitle').textContent, 'New collection');
    assert.equal(element('textPromptLabel').textContent, 'Name');
    assert.equal(element('textPromptOk').textContent, 'Create');
    assert.equal(element('textPromptInput').value, 'Draft');
    assert.equal(element('textPromptInput').focused && element('textPromptInput').selected, true);
    context.finishTextPrompt('Keepers');
    assert.equal(await answer, 'Keepers');
    assert.equal(element('textPromptOverlay').classList.contains('open'), false);
});

test('cancel resolves with null and a second dialog cancels the first', async () => {
    const {context} = dialog();
    const first = context.askText('Save to Prompt Library', 'Title', 'Untitled', 'Save');
    const second = context.askText('New collection', 'Name', '', 'Create');
    assert.equal(await first, null);
    context.finishTextPrompt(null);
    assert.equal(await second, null);
});

test('Gallery no longer calls window.prompt()', () => {
    const code = script.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
    assert.doesNotMatch(code, /(^|[^.\w])prompt\(/);
    assert.match(code, /await askText\('New collection', 'Name', '', 'Create'\)/);
    assert.match(code, /await askText\('Save to Prompt Library', 'Title', /);
    assert.match(body, /id="textPromptOverlay"/);
});

test('Gallery shortcuts stay off while the text dialog is open', () => {
    const keydown = script.slice(script.indexOf("document.addEventListener('keydown'"));
    const guard = keydown.indexOf("getElementById('textPromptOverlay').classList.contains('open')");
    assert.ok(guard > 0 && guard < keydown.indexOf("var lbOpen"));
});

test('every localStorage access is guarded', () => {
    const lines = script.split('\n').filter(line => line.includes('localStorage.'));
    assert.ok(lines.length > 10);
    // Multi-line try blocks: the two known ones open "try {" on the line before.
    const allowed = ["localStorage.setItem(GALLERY_STATE_KEY", "localStorage.getItem('gallerySelectedImage')"];
    for (const line of lines) {
        if (allowed.some(item => line.includes(item))) continue;
        assert.match(line, /try|readStored/, line.trim());
    }
    const read = functionSource('readStored');
    const context = {localStorage: {getItem() { throw new Error('SecurityError'); }}};
    vm.createContext(context);
    vm.runInContext(read, context);
    assert.equal(context.readStored('galleryGroupMode', 'none'), 'none');
});

test('delete wording names the trash of the computer that runs CyberHub', () => {
    assert.match(script, /will be moved to the trash on the computer that runs CyberHub\./);
    assert.doesNotMatch(body, /your system trash/);
});
