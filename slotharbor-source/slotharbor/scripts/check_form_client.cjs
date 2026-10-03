/* Test typed form serialization without a network or browser dependency. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const keys = [{}, {}, {}];
const context = vm.createContext({
  crypto: webcrypto,
  document: {querySelectorAll: selector => selector === '[data-request-key]' ? keys : []},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../slotharbor/static/app.js'), 'utf8'), context);
const field = (name, value, type) => ({name, value, dataset: {type}});
context.form = {elements: [
  field('resource_id', '3', 'int'), field('title', 'Review', undefined),
  field('start_fold', '', 'nullable-int'), field('active', 'false', 'bool'),
  {name:'weekdays',dataset:{type:'ints'},selectedOptions:[{value:'0'},{value:'4'}]},
]};
const payload = JSON.parse(vm.runInContext('JSON.stringify(payloadFor(form))', context));
assert.deepEqual(payload, {resource_id:3,title:'Review',start_fold:null,active:false,weekdays:[0,4]});
assert.equal(new Set(keys.map(k => k.value)).size, 3);
assert(keys.every(k => /^[a-f0-9]{48}$/.test(k.value)));
console.log('Form serialization and independently generated request keys passed.');
