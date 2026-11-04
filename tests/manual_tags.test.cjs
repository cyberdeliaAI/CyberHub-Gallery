const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../modules/gallery/__init__.py'), 'utf8');

function functionSource(name) {
    const re = new RegExp('^(?:async )?function ' + name + '\\(', 'm');
    const match = re.exec(source);
    assert.ok(match, name);
    const brace = source.indexOf('{', match.index);
    let depth = 0, quote = '', comment = '';
    for (let i = brace; i < source.length; i++) {
        const c = source[i], pair = source.slice(i, i + 2);
        if (comment === 'line') { if (c === '\n') comment = ''; }
        else if (comment === 'block') { if (pair === '*/') { comment = ''; i++; } }
        else if (quote) { if (c === '\\') i++; else if (c === quote) quote = ''; }
        else if (pair === '//') { comment = 'line'; i++; }
        else if (pair === '/*') { comment = 'block'; i++; }
        else if ('\'"`'.includes(c)) quote = c;
        else if (c === '{') depth++;
        else if (c === '}' && --depth === 0) return source.slice(match.index, i + 1);
    }
    throw Error(name);
}
function install(context, ...names) {
    vm.createContext(context);
    names.forEach(name => vm.runInContext(functionSource(name), context));
    return context;
}

test('manual labels normalize whitespace/case and keep underscores and Unicode',()=>{
    const c=install({},'parseManualTags');
    assert.deepEqual(Array.from(c.parseManualTags(' Great Pose, great_pose, , Café, great_clothes ')),
                     ['great_pose','café','great_clothes']);
});

test('manual filter discards a late result after the user changes view',async()=>{
    let resolve;
    const rendered=[];
    const c=install({manualTagFilter:['great_pose','great_clothes'],manualTagFolder:'Images/a_b',
        galleryRequestId:0,currentPage:1,activateSpecialView(){},updateManualFilterButton(){},
        document:{getElementById(){return {value:'date-desc'}}},modelInfoParam(){return ''},
        metadataFilterParam(){return '&metadata=all'},
        fetchGalleryData(url){assert.match(url,/tags=great_pose%2Cgreat_clothes/);return new Promise(r=>resolve=r)},
        renderGalleryFiles(){rendered.push('old')}
    },'loadManualTagView');
    const pending=c.loadManualTagView(true);
    c.galleryRequestId++;
    resolve({files:[{path:'old.png'}],total:1});await pending;
    assert.deepEqual(rendered,[]);
});

test('batch mutation snapshots paths and tags and prevents overlapping writes',async()=>{
    let resolve;
    const calls=[],refreshed=[];
    const c=install({manualTagBusy:false,selectedFile:'Images/a.png',specialView:null,
        document:{querySelectorAll(){return []}},
        API:{post(url,body){calls.push(body);return new Promise(r=>resolve=r)}},
        showToast(){},loadImageManualTags(path){refreshed.push(path)}
    },'setManualTagBusy','changeManualTags');
    const paths=['Images/a.png'],tags=['great_pose'];
    const pending=c.changeManualTags(paths,tags,'add');
    paths[0]='Images/b.png';tags[0]='different';c.selectedFile='Images/b.png';
    assert.equal(await c.changeManualTags(paths,tags,'remove'),null);
    assert.equal(calls.length,1);
    assert.deepEqual(Array.from(calls[0].paths),['Images/a.png']);
    assert.deepEqual(Array.from(calls[0].tags),['great_pose']);
    resolve({ok:true,matched:1,skipped:0});await pending;
    assert.deepEqual(refreshed,['Images/b.png']);
    assert.equal(c.manualTagBusy,false);
});

test('failed mutations keep the current tag editor contents for correction',async()=>{
    const c=install({manualTagBusy:false,selectedFile:'Images/a.png',specialView:null,
        document:{querySelectorAll(){return []}},API:{post:async()=>null},showToast(){},
        loadImageManualTags(){throw Error('Would discard typed labels')}
    },'setManualTagBusy','changeManualTags');
    assert.equal(await c.changeManualTags(['Images/a.png'],['too-long'],'add'),null);
    assert.equal(c.manualTagBusy,false);
});

test('late tag reads cannot overwrite the newly selected image',async()=>{
    const resolves=[],section={innerHTML:''};
    const c=install({manualImageTagRequest:0,selectedFile:'Images/a.png',
        document:{getElementById(){return section}},API:{get(){return new Promise(r=>resolves.push(r))}}
    },'loadImageManualTags');
    const a=c.loadImageManualTags('Images/a.png');c.selectedFile='Images/b.png';
    const b=c.loadImageManualTags('Images/b.png');
    resolves[0]({tags:['stale_tag']});await a;
    assert.equal(section.innerHTML,'');
    resolves[1](null);await b;
    assert.match(section.innerHTML,/unavailable/);
    assert.doesNotMatch(section.innerHTML,/stale_tag/);
});

test('clearing a manual filter resets the breadcrumb and restores the folder',()=>{
    const calls=[];
    const c=install({manualTagFilter:['great_pose'],manualTagFolder:'Images/old',currentFolder:'Images/new',
        document:{getElementById(){return {close(){calls.push('close')}}}},clearSpecialView(){calls.push('clear')},
        updateManualFilterButton(){},updateBreadcrumb(path){calls.push(['breadcrumb',path])},
        loadGallery(path){calls.push(['folder',path])}
    },'clearManualTagFilter');
    c.clearManualTagFilter();
    assert.deepEqual(Array.from(c.manualTagFilter),[]);
    assert.equal(c.manualTagFolder,'');
    assert.deepEqual(calls.slice(-2),[['breadcrumb','Images/new'],['folder','Images/new']]);
});
