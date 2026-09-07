// Run with: node --test tests/gallery_layout.test.cjs (no npm dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../modules/gallery/__init__.py'), 'utf8');

function element(ratio, header = false) {
    const classes = new Set(header ? ['gallery-group-header'] : ['thumb-card']);
    const style = {removeProperty(key) { delete this[key]; }};
    return {
        dataset: {aspectRatio: ratio}, style,
        classList: {contains: key => classes.has(key), toggle(key, on) { on ? classes.add(key) : classes.delete(key); }},
        get offsetLeft() { return parseFloat(style.left) || 0; },
        get offsetTop() { return parseFloat(style.top) || 0; },
        get offsetWidth() { return parseFloat(style.width) || 0; },
        get offsetHeight() { return header ? 40 : parseFloat(style.height) || 0; },
    };
}

function setup(items, width = 600) {
    const grid = Object.assign(element(1), {children: items, clientWidth: width});
    const context = vm.createContext({
        galleryLayout: 'masonry',
        document: {getElementById: () => grid, documentElement: {}},
        getComputedStyle: () => ({getPropertyValue: () => '180px'}),
    });
    for (const name of ['layoutGallery', 'getMasonryArrowTargetIndex', 'getArrowTargetIndex']) {
        const start = source.indexOf('function ' + name + '(');
        assert.ok(start >= 0, name + ' exists');
        vm.runInContext(source.slice(start, source.indexOf('\nfunction ', start + 1)), context);
    }
    context.layoutGallery();
    return {grid, context};
}

function assertNoOverlap(items, width) {
    items.forEach((a, i) => {
        assert.ok(a.offsetLeft >= 0);
        assert.ok(a.offsetLeft + a.offsetWidth <= width + .01);
        items.slice(i + 1).forEach(b => {
            assert.ok(a.offsetLeft + a.offsetWidth <= b.offsetLeft + .01 ||
                b.offsetLeft + b.offsetWidth <= a.offsetLeft + .01 ||
                a.offsetTop + a.offsetHeight <= b.offsetTop + .01 ||
                b.offsetTop + b.offsetHeight <= a.offsetTop + .01,
                'cards and headings must not overlap');
        });
    });
}

test('mixed ratios keep composition and DOM order across wide and narrow layouts', () => {
    const items = [2 / 3, 1.5, 1, .25, 4, 1.2, .8, 1].map(r => element(r));
    const original = items.slice();
    const {grid, context} = setup(items);
    for (const width of [1100, 600, 370, 90]) {
        grid.clientWidth = width;
        context.layoutGallery();
        assert.deepEqual(items, original);
        assertNoOverlap(items, width);
        items.forEach((item, i) => {
            assert.ok(Math.abs((item.offsetWidth - 4) / (item.offsetHeight - 4) - item.dataset.aspectRatio) < 1e-8);
            if (i) assert.ok(item.offsetTop >= items[i - 1].offsetTop - .01);
        });
        assert.ok(parseFloat(grid.style.height) >= Math.max(...items.map(c => c.offsetTop + c.offsetHeight)) - .01);
    }
});

test('model headings span all columns and separate groups after resize', () => {
    const items = [element(1, true), element(.5), element(2), element(1, true), element(1), element(.7)];
    const {grid, context} = setup(items);
    for (const width of [600, 250]) {
        grid.clientWidth = width;
        context.layoutGallery();
        assertNoOverlap(items, width);
        assert.equal(items[3].offsetWidth, width);
        assert.ok(items[3].offsetTop >= Math.max(items[1].offsetTop + items[1].offsetHeight, items[2].offsetTop + items[2].offsetHeight));
        assert.ok(items[4].offsetTop >= items[3].offsetTop + items[3].offsetHeight);
    }
});

test('missing dimensions start square and relayout once a thumbnail provides them', () => {
    const items = [element(undefined), element(1), element(1), element(1)];
    const {context} = setup(items);
    assert.equal(items[0].offsetWidth, items[0].offsetHeight);
    items[0].dataset.aspectRatio = .5;
    context.layoutGallery();
    assert.ok(items[0].offsetHeight > items[0].offsetWidth);
    assertNoOverlap(items, 600);
});

test('Grid removes positioning without replacing selection or fetching images', () => {
    const items = [element(.5), element(2)];
    items[0].classList.toggle('selected', true);
    items[1].classList.toggle('multi-selected', true);
    const {grid, context} = setup(items);
    context.galleryLayout = 'grid';
    context.layoutGallery();
    for (const item of items) for (const prop of ['left', 'top', 'width', 'height']) assert.equal(item.style[prop], undefined);
    assert.equal(grid.style.height, undefined);
    assert.ok(items[0].classList.contains('selected'));
    assert.ok(items[1].classList.contains('multi-selected'));
});

test('empty and temporarily hidden galleries are safe to lay out', () => {
    const {grid, context} = setup([]);
    assert.equal(grid.style.height, '0px');
    grid.children = [element(.5)];
    grid.clientWidth = 0;
    context.layoutGallery();
    assert.equal(grid.children[0].style.height, undefined);
    grid.clientWidth = 600;
    context.layoutGallery();
    assert.ok(parseFloat(grid.children[0].style.height) > 0);
});

test('arrows follow visible neighbours and remain at boundaries', () => {
    const items = [.5, 2, 1, 1, 1, 1].map(r => element(r));
    const {context} = setup(items);
    const target = (index, key) => context.getArrowTargetIndex(items, index, 3, key);
    assert.equal(target(1, 'ArrowDown'), 3);
    assert.equal(target(3, 'ArrowUp'), 1);
    assert.equal(target(0, 'ArrowRight'), 3, 'nearest vertical centre in the next column');
    assert.equal(target(3, 'ArrowLeft'), 0);
    assert.equal(target(0, 'ArrowUp'), 0);
    assert.equal(target(0, 'ArrowLeft'), 0);
    assert.equal(target(0, 'Enter'), 0);
    context.galleryLayout = 'grid';
    assert.equal(target(1, 'ArrowDown'), 4, 'Grid retains row-based navigation');
});
