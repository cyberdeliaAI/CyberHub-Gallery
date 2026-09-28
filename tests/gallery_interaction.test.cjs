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
function selection() {
    const requests = [], rendered = [], timers = [];
    const img = {addEventListener(){}};
    const panel = {innerHTML:'', querySelector(){return img}};
    const context = install({
        selectedFile:null, selectionAnchorFile:null, metaRequestId:0, metaAbort:null,
        metaRefreshTimer:null, metaCache:{}, currentFiles:[], window:{}, AbortController,
        localStorage:{setItem(){}}, scheduleGalleryStateSave(){}, setMetaPanelCollapsed(){},
        document:{querySelectorAll(){return []},getElementById(){return panel}},
        escHtml:s=>s, escAttr:s=>s, prepareThumbnail(){},
        setTimeout(fn,ms){timers.push({fn,ms});return timers.length}, clearTimeout(){},
        API:{get(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}},
        renderMetaPanel(meta,path){rendered.push(path)},
    }, 'thumbnailUrl', 'selectImage');
    const flush = async()=>{ timers.splice(0).filter(t=>t.ms===80).forEach(t=>t.fn()); await Promise.resolve(); };
    return {context,requests,rendered,panel,flush};
}
test('late metadata cannot overwrite the latest selection or its delete target', async()=>{
    const x=selection();
    const a=x.context.selectImage('Images/a.png',null); await x.flush();
    const b=x.context.selectImage('Images/b.png',null); await x.flush();
    assert.equal(x.requests[0].options.signal.aborted,true);
    x.requests[1].resolve({info:{name:'b.png'}}); await b;
    x.requests[0].resolve({info:{name:'a.png'}}); await a;
    assert.deepEqual(x.rendered,['Images/b.png']);
    assert.equal(x.context.selectedFile,'Images/b.png');
    assert.equal(x.context.metaCache['Images/a.png'],undefined);
});
test('rapid multi-select focus changes coalesce metadata requests and preview thumbnails immediately',async()=>{
    const x=selection();
    const selections=['a','b','c'].map(name=>x.context.selectImage('Images/'+name+'.png',null,true));
    assert.match(x.panel.innerHTML,/\/thumb\/Images%2Fc.png/);
    assert.doesNotMatch(x.panel.innerHTML,/\/image\//);
    await x.flush();
    assert.equal(x.requests.length,1);
    x.requests[0].resolve({info:{name:'c.png'}});
    await Promise.all(selections);
    assert.deepEqual(x.rendered,['Images/c.png']);
});
test('late missing metadata does not blank the newer selection',async()=>{
    const x=selection();
    const a=x.context.selectImage('Images/a.png',null); await x.flush();
    const b=x.context.selectImage('Images/b.png',null); await x.flush();
    x.requests[1].resolve({info:{name:'b.png'}}); await b;
    const panel=x.panel.innerHTML;
    x.requests[0].resolve(null); await a;
    assert.equal(x.panel.innerHTML,panel);
    assert.deepEqual(x.rendered,['Images/b.png']);
});
test('late gallery responses are discarded and outstanding requests always settle',async()=>{
    const resolvers=[];
    const c=install({galleryRequestId:1,galleryRequestsInFlight:0,API:{get(){return new Promise(resolve=>resolvers.push(resolve))}}},'fetchGalleryData');
    const old=c.fetchGalleryData('/old',1);
    c.galleryRequestId=2;
    const fresh=c.fetchGalleryData('/new',2);
    resolvers[1]({files:['new']});
    assert.deepEqual(await fresh,{files:['new']});
    resolvers[0]({files:['old']});
    assert.equal(await old,null);
    assert.equal(c.galleryRequestsInFlight,0);
});

function rendering() {
    const area={scrollTop:0,getBoundingClientRect(){return {top:0}}};
    const grid={children:[],style:{},
        querySelectorAll(){return this.children.filter(c=>c.dataset.path)},
        replaceChildren(){this.children=[]},
        insertBefore(card,before){this.children=this.children.filter(c=>c!==card);const i=before?this.children.indexOf(before):this.children.length;this.children.splice(i,0,card)},
    };
    const elements={galleryGrid:grid,galleryArea:area};
    for(const id of ['galleryEmpty','galleryToolbar','galleryCount','pagination']) elements[id]={style:{},textContent:''};
    function card(file,index) {
        const classes=new Set();
        const c={dataset:{path:file.path,index,renderKey:JSON.stringify(file)+':none'},
            classList:{toggle(key,on){if(on)classes.add(key);else classes.delete(key)},contains(key){return classes.has(key)}},
            querySelector(){return null},
            getBoundingClientRect(){const top=grid.children.indexOf(c)*100-area.scrollTop;return {top,bottom:top+100}},
            remove(){grid.children=grid.children.filter(x=>x!==c)},
        };
        return c;
    }
    const context=install({
        document:{getElementById(id){return elements[id]}},galleryThumbObserver:null,galleryGroupMode:'none',
        lastGalleryTotal:0,selectedFile:'a',multiSelected:new Set(['a']),pendingDeletePaths:new Set(),metadataFilter:'all',
        currentPage:1,totalPages:1,createThumbCard:card,
        IntersectionObserver:class{observe(){}disconnect(){}},
        layoutGallery(){},restoreGalleryScrollIfNeeded(){},scheduleGalleryStateSave(){},updateToolbarNav(){},showGalleryPlaceholder(){},
        findThumbCard(path){return grid.children.find(c=>c.dataset.path===path)},
    },'renderGalleryFiles');
    return {context,grid,area};
}
test('live updates preserve existing card nodes, selection and the visible scroll anchor',()=>{
    const x=rendering();
    x.context.renderGalleryFiles([{path:'a'},{path:'b'}],2,false,false);
    const [a,b]=x.grid.children;
    x.context.renderGalleryFiles([{path:'new'},{path:'a'},{path:'b'}],3,false,true);
    assert.equal(x.grid.children[1],a);
    assert.equal(x.grid.children[2],b);
    assert.equal(a.classList.contains('selected'),true);
    assert.equal(a.classList.contains('multi-selected'),true);
    assert.equal(x.area.scrollTop,100);
});
test('completed processing refreshes only the changed card and empty results clear stale cards',()=>{
    const x=rendering();
    x.context.renderGalleryFiles([{path:'a',processing:true},{path:'b'}],2,false,false);
    const [a,b]=x.grid.children;
    x.context.renderGalleryFiles([{path:'a',processing:false},{path:'b'}],2,false,true);
    assert.notEqual(x.grid.children[0],a);
    assert.equal(x.grid.children[1],b);
    x.context.renderGalleryFiles([],0,false,true);
    assert.equal(x.grid.children.length,0);
});
