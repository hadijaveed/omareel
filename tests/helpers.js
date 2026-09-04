// Pure QML helper regressions, no desktop session required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = process.env.OMAREEL_HELPER_SOURCE || path.join(__dirname, '..', 'Omareel.js');
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync(source, 'utf8').replace(/^\.pragma library\s*/, ''), ctx);
const plain = value => JSON.parse(JSON.stringify(value));
const screen = {x:0,y:0,width:1800,height:1300};
const region = '1447x1240+7+33';
assert.equal(ctx.cardPlacement({phase:'recording',region},screen,620,72,55,28),null);
for (const phase of ['processing','uploading','done']) {
  assert.deepEqual(plain(ctx.cardPlacement({phase,region},screen,620,72,55,28)),{x:590,y:55});
}
assert.deepEqual(plain(ctx.cardPlacement({phase:'recording',region:'1800x1000+0+0'},screen,620,72,55,28)),{x:590,y:1200});
assert.deepEqual(plain(ctx.regionOf({region:'1920x1080+-1920+0'})),{w:1920,h:1080,x:-1920,y:0});
assert.equal(ctx.get({mic:false},'mic',true),false);
assert.equal(ctx.deviceLabel([{value:'auto',label:'First available camera'}],'/dev/video99'),'Unavailable — choose another device');
assert.deepEqual(plain(ctx.deviceOptions([{value:'auto',label:'First available camera'}],'/dev/video99')),
  [{value:'/dev/video99',label:'Unavailable — choose a device'},{value:'auto',label:'First available camera'}]);
assert.equal(ctx.deviceOptions([{value:'auto',label:'First available camera'}],'auto').length,1);
assert.equal(ctx.statusText({phase:'starting'},0),'Starting camera and screen capture…');
assert.equal(ctx.statusText({phase:'error',error:'Camera unavailable'},0),'Camera unavailable');
assert.equal(ctx.statusText({phase:'processing'},0),'Preparing your video…');
assert.equal(ctx.canUpload({phase:'starting',canUpload:true}),false);
const original={webcamPosition:'top-right',upload:{auto:false}};
assert.deepEqual(plain(ctx.withValue(original,'upload.auto',true)),{webcamPosition:'top-right',upload:{auto:true}});
assert.equal(original.upload.auto,false);
assert.equal(ctx.canUpload({phase:'done',file:'take.mp4',canUpload:true}),true);
assert.equal(ctx.canUpload({phase:'recording',canUpload:true}),false);
assert.equal(ctx.shareTarget({file:'take.mp4',url:'https://example.test/demo'}),'https://example.test/demo');
const sharing = {upload:{provider:'s3',bucket:'recordings',region:'us-east-1'}};
const ready = {ready:true,config:sharing.upload};
assert.equal(ctx.uploadReady(sharing,ready),true);
assert.equal(ctx.uploadReady(sharing,{ready:false,config:sharing.upload}),false);
assert.equal(ctx.uploadReady({upload:{...sharing.upload,provider:'r2'}},ready),false);
assert.equal(ctx.uploadReady({upload:{...sharing.upload,prefix:'new'}},ready),false);
assert.equal(ctx.uploadReady({upload:{provider:'existing',remote:'missing:path'}},{}),false);
console.log('PASS: saved actions, live card exclusion, signed coordinates, config toggles, and sharing helpers');
