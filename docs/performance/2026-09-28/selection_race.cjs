// Execute the unmodified async selection function with controlled response order.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync('/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py','utf8');
const start=source.indexOf('async function selectImage(');
const end=source.indexOf('\nfunction renderMetaPanel(',start);
const requests=[];
const renders=[];
const panel={innerHTML:''};
const context={
    selectedFile:null, selectionAnchorFile:null, metaCache:{},
    localStorage:{setItem(){}}, scheduleGalleryStateSave(){}, setMetaPanelCollapsed(){},
    document:{querySelectorAll(){return []},getElementById(){return panel}},
    API:{get(url){return new Promise(resolve=>requests.push({url,resolve}))}},
    renderMetaPanel(meta,path){renders.push(path)},setTimeout,
};
vm.createContext(context);
vm.runInContext(source.slice(start,end),context);
(async()=>{
    const a=context.selectImage('older.png',null);
    const b=context.selectImage('newest.png',null);
    requests[1].resolve({info:{name:'newest.png'},parsed:{prompt:'new'}});
    await b;
    requests[0].resolve({info:{name:'older.png'},parsed:{prompt:'old'}});
    await a;
    assert.equal(context.selectedFile,'newest.png');
    assert.equal(renders.at(-1),'older.png');
    const result={reproduced:true, selected:context.selectedFile, rendered:renders.at(-1),
                  requests:requests.length, rendering_order:renders,
                  interpretation:'An older metadata response overwrites the current selection panel.'};
    fs.writeFileSync(require('node:path').join(__dirname,'selection-race.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
})();
