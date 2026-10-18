/* ViewPilot front end — ES5 for Revit's Windows Forms WebBrowser host.
   NO network requests, external libraries or remote scripts. */
var state={views:[],scopes:[],templates:[],presets:{},settings:{humor:true},
  rows:{},filter:{},tab:'rename',project:'',version:'',expanded:{},advanced:{},
  health:null,busy:false,hostReady:false,unitSystem:'metric'};
var categories=['Floor Plans','Structural Plans','Ceiling Plans','Area Plans','Sections',
 'Elevations','Detail Views','Drafting Views','Legends','3D Views','Schedules','Other Views'];
var METHOD_NAMES={none:'No Duplicate',duplicate:'Duplicate',detailing:'Duplicate with Detailing',dependent:'Duplicate as Dependent'};
var humorLines=[
 "Revit isn't frozen. It's just thinking about its life choices.",
 'One small change, 47 new warnings. Welcome to Revit!',
 "Trust me, I'm a BIM Engineer. Famous last words!",
 'Revit crashed. At least something finished today.',
 'The architect moved the grid. The beams requested therapy.',
 'Duplicate as Dependent. Independence was never an option.',
 'Your views are multiplying faster than your deadlines!',
 'Revit knows what you want. It just refuses to cooperate.',
 'Coffee first. Constraints later.',
 'Everything is perfectly aligned... in one view.',
 'The architect said "minor revision." The model said otherwise.',
 'ViewPilot is doing the clicking your mouse refused to do.',
 'Dear Architect, gravity is not an optional parameter.',
 'Level 01, Level 1, L1... Three names, one floor.',
 'The detail looked perfect until I changed the scale.',
 'The linked model moved. Again. Nobody act surprised.',
 'Your model has 99 problems, and constraints caused 98.',
 "The view is duplicated. The deadline isn't.",
 'Revit is not responding. Neither am I before coffee.'
];
function el(id){return document.getElementById(id);}
function h(s){return String(s===undefined || s===null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function clone(obj){return JSON.parse(JSON.stringify(obj));}
function arrContains(a,x){for(var i=0;i<a.length;i++){if(a[i]===x)return true;}return false;}
function getView(id){for(var i=0;i<state.views.length;i++){if(state.views[i].id===String(id))return state.views[i];}return null;}
function sortedIds(){var result=[];for(var k in state.rows){if(state.rows.hasOwnProperty(k)&&state.rows[k].checked)result.push(k);}return result;}
function option(value,label,selected){return '<option value="'+h(value)+'"'+(String(value)===String(selected)?' selected':'')+'>'+h(label)+'</option>';}
function scopeOptions(selected,allowed){var out=option('default','Default (source)',selected)+option('none','None',selected);
 if(!allowed)return option('default','N/A',selected);
 for(var i=0;i<state.scopes.length;i++)out+=option(state.scopes[i].id,state.scopes[i].name,selected);
 return out;}
function templateOptions(selected){var out=option('default','Default (source)',selected)+option('none','None',selected);
 for(var i=0;i<state.templates.length;i++)out+=option(state.templates[i].id,state.templates[i].name,selected);return out;}
function methodsOptions(view,selected){var out=option('none','No Duplicate',selected);for(var i=0;i<view.methods.length;i++)out+=option(view.methods[i],METHOD_NAMES[view.methods[i]],selected);return out;}
function methodFor(view){return view.methods.length ? view.methods[0]:'none';}
function newRow(v){return {checked:false,newName:v.name,method:'none',count:1,scope:'default',copies:[]};}
function newCopy(v,index,method){var name=v.name+' - '+('0'+(index+1)).slice(-2);return {baseName:name,name:name,method:method,scope:'default',template:'default',scale:'default',crop:'default',prefix:'',suffix:'',manual:false};}
function setHostData(raw){
 var data=typeof raw==='string'?JSON.parse(raw):raw;
 state.views=data.views||[];state.scopes=data.scopeBoxes||[];state.templates=data.templates||[];
 state.presets=data.presets||{};state.settings=data.settings||{humor:true};state.project=data.project||'';
 state.version=data.version||'';state.rows={};state.expanded={};state.advanced={};
 for(var i=0;i<state.views.length;i++)state.rows[state.views[i].id]=newRow(state.views[i]);
 for(var j=0;j<categories.length;j++)state.filter[categories[j]]=true;
 state.hostReady=true;state.busy=false;
 el('projectName').innerHTML=h(state.project)+' · Revit '+h(state.version);
 el('humorToggle').checked=state.settings.humor!==false;
 setPresets(state.presets);renderFilters();renderRows();renderSummary();
}
function demoData(){
 var types=[['Floor Plans','FloorPlan','Level 1'],['Floor Plans','FloorPlan','Level 2'],
  ['Structural Plans','EngineeringPlan','Foundation Plan'],['Area Plans','AreaPlan','Area 1'],['Ceiling Plans','CeilingPlan','Level 1 RCP'],
  ['Sections','Section','Section A'],['3D Views','ThreeD','3D Coordination'],
  ['Drafting Views','DraftingView','SAPP Drafting Template'],['Legends','Legend','Foundation Notes'],
  ['Schedules','Schedule','Footing Schedule']];
 var views=[];for(var i=0;i<types.length;i++)views.push({id:String(i+1),category:types[i][0],type:types[i][1],name:types[i][2],
 methods:types[i][0]==='Legends'||types[i][0]==='Schedules'?['duplicate']:types[i][0]==='3D Views'?['duplicate','detailing']:['duplicate','detailing','dependent'],
 scope:'none',can_scope:types[i][0]!=='Legends'&&types[i][0]!=='Schedules',
 can_edit_scope:true,valid_templates:['61','62'],template:'none',scale:100,sheet:'',crop:true,dependent:false});
 return{project:'DEMO – Open from pyRevit to access actual Revit data',version:'2022+',unitSystem:'imperial',views:views,
 scopeBoxes:[{id:'51',name:'East Wing'},{id:'52',name:'West Wing'}],
 templates:[{id:'61',name:'Structural Plan - Standard'},{id:'62',name:'Working Plan'}],presets:{},settings:{humor:true}};
}
function host(action,payload){
 if(!window.__inRevitHost){alert('This is the offline UI preview. Launch the pushbutton from Revit to perform '+action+'.');return;}
 var packet=JSON.stringify({action:action,payload:payload||{}});
 el('bridge_payload').innerText=packet;
 window.location.href='http://ndevpilot.invalid/bridge?r='+new Date().getTime()+'&action='+encodeURIComponent(action);
}
function renderFilters(){
 var content='<label><input type="checkbox" '+(allFilterChecked()?'checked':'')+' onclick="setAllFilters(this.checked)"> All Views</label>';
 var counts={};for(var j=0;j<state.views.length;j++)counts[state.views[j].category]=(counts[state.views[j].category]||0)+1;
 for(var i=0;i<categories.length;i++){
  var name=categories[i];if(!counts[name])continue;
  content+='<label><input type="checkbox" '+(state.filter[name]?'checked':'')+' onclick="setFilter(\''+h(name)+'\',this.checked)"> '+h(name)+' <span class="muted tiny">'+counts[name]+'</span></label>';
 }
 el('categoryFilters').innerHTML=content;
}
function allFilterChecked(){for(var i=0;i<categories.length;i++)if(!state.filter[categories[i]])return false;return true;}
function setAllFilters(value){for(var i=0;i<categories.length;i++)state.filter[categories[i]]=value;renderFilters();renderRows();}
function setFilter(cat,value){state.filter[cat]=value;renderFilters();renderRows();}
function visibleViews(){var q=el('searchInput').value.toLowerCase().replace(/^\s+|\s+$/g,'');var result=[];
 for(var i=0;i<state.views.length;i++){
  var v=state.views[i];if(!state.filter[v.category])continue;
  var hay=(v.name+' '+v.category+' '+v.sheet+' '+v.type).toLowerCase();
  if(q&&hay.indexOf(q)<0)continue;result.push(v);
 }return result;
}
function checkVisible(val){var views=visibleViews();for(var i=0;i<views.length;i++)state.rows[views[i].id].checked=val;renderRows();renderSummary();}
function selectView(id,checked){state.rows[id].checked=checked;renderRows();renderSummary();}
function changeOriginalName(id,value){state.rows[id].newName=value;renderSummary();}
function changeParentScope(id,val){state.rows[id].scope=val;renderSummary();}
function changeMethod(id,method){var row=state.rows[id],v=getView(id);row.method=method;row.checked=true;
 if(method==='none'){row.copies=[];state.expanded[id]=false;}
 else{setCopiesCount(id,row.count,true);state.expanded[id]=true;}
 renderRows();renderSummary();
}
function setCopiesCount(id,count,skipRender){var row=state.rows[id],v=getView(id);var number=parseInt(count,10);
 if(isNaN(number)||number<1)number=1;if(number>100)number=100;row.count=number;
 if(row.method==='none'){row.copies=[];return;}
 while(row.copies.length<number)row.copies.push(newCopy(v,row.copies.length,row.method));
 while(row.copies.length>number)row.copies.pop();
 row.checked=true;state.expanded[id]=true;
 if(!skipRender){renderRows();renderSummary();}
}
function expandRow(id){state.expanded[id]=!state.expanded[id];renderRows();}
function advancedToggle(id,idx){var key=id+':'+idx;state.advanced[key]=!state.advanced[key];renderRows();}
function childChange(id,idx,key,value){var cp=state.rows[id].copies[idx];if(!cp)return;
 cp[key]=value;
 if(key==='name')cp.manual=true;
 if(key==='prefix'||key==='suffix'){cp.manual=false;cp.name=(cp.prefix||'')+cp.baseName+(cp.suffix||'');}
 if(key==='method'&&value==='none'){cp.method=methodFor(getView(id));}
 renderSummary();
}
function removeCopy(id,idx){var row=state.rows[id];row.copies.splice(idx,1);row.count=row.copies.length;
 if(!row.count){row.method='none';row.count=1;state.expanded[id]=false;}
 renderRows();renderSummary();
}
function parentRow(v){var r=state.rows[v.id],methods=r.method==='none'?0:r.copies.length;
 var cls=r.checked?'parent selected':'parent';
 var expand=r.copies.length?'<span class="expander" onclick="expandRow(\''+v.id+'\')">'+(state.expanded[v.id]?'&#9662;':'&#9656;')+'</span>':'';
 var result='<tr class="'+cls+'">'+
 '<td class="checkcol"><input type="checkbox" '+(r.checked?'checked':'')+' onclick="selectView(\''+v.id+'\',this.checked)"></td>'+
 '<td>'+expand+h(v.category)+(v.sheet?'<div class="muted tiny">Sheet '+h(v.sheet)+'</div>':'')+'</td>'+
 '<td>'+h(v.name)+'</td>'+
 '<td><input type="text" title="Rename original view" value="'+h(r.newName)+'" oninput="changeOriginalName(\''+v.id+'\',this.value)"></td>'+
 '<td><select onchange="changeMethod(\''+v.id+'\',this.value)">'+methodsOptions(v,r.method)+'</select></td>'+
 '<td><input type="number" min="1" max="100" '+(r.method==='none'?'disabled':'')+' value="'+h(r.count)+'" onchange="setCopiesCount(\''+v.id+'\',this.value)"></td>'+
 '<td><select '+(v.can_scope?'':'disabled')+' onchange="changeParentScope(\''+v.id+'\',this.value)">'+scopeOptions(r.scope,v.can_scope)+'</select></td>'+
 '<td>'+(r.checked?'<span class="status-info">'+(methods?'+'+methods+' copies':'Ready')+'</span>':'<span class="muted">—</span>')+'</td></tr>';
 if(r.copies.length&&state.expanded[v.id]){
  for(var i=0;i<r.copies.length;i++)result+=childRows(v,i,r.copies[i]);
 }
 return result;
}
function viewScaleOptions(view,selected){
 var imperial=[['384','1/32\" = 1\'-0\"'],['192','1/16\" = 1\'-0\"'],['128','3/32\" = 1\'-0\"'],['96','1/8\" = 1\'-0\"'],['64','3/16\" = 1\'-0\"'],['48','1/4\" = 1\'-0\"'],['32','3/8\" = 1\'-0\"'],['24','1/2\" = 1\'-0\"'],['16','3/4\" = 1\'-0\"'],['12','1\" = 1\'-0\"'],['8','1 1/2\" = 1\'-0\"'],['4','3\" = 1\'-0\"']];
 var metric=[10,20,25,50,75,100,125,150,200,250,500,1000];
 var sourceScale=Number(view.scale||0),currentLabel=state.unitSystem==='imperial'?imperialScaleLabel(sourceScale):'1:'+sourceScale;
 var output=option('default','Default (source: '+currentLabel+')',selected);
 if(sourceScale>0 && selected!=='default')output+=option(String(sourceScale),'Source ('+currentLabel+')',selected);
 if(state.unitSystem==='imperial'){
  for(var i=0;i<imperial.length;i++)output+=option(imperial[i][0],imperial[i][1],selected);
 }else{
  for(var j=0;j<metric.length;j++)output+=option(String(metric[j]),'1:'+metric[j],selected);
 }
 return output;
}
function imperialScaleLabel(ratio){
 var maps={'384':'1/32\" = 1\'-0\"','192':'1/16\" = 1\'-0\"','128':'3/32\" = 1\'-0\"','96':'1/8\" = 1\'-0\"','64':'3/16\" = 1\'-0\"','48':'1/4\" = 1\'-0\"','32':'3/8\" = 1\'-0\"','24':'1/2\" = 1\'-0\"','16':'3/4\" = 1\'-0\"','12':'1\" = 1\'-0\"','8':'1 1/2\" = 1\'-0\"','4':'3\" = 1\'-0\"'};
 return maps[String(ratio)]||'1:'+ratio;
}
function childRows(v,index,cp){var key=v.id+':'+index;
 var res='<tr class="child"><td></td><td colspan="7"><div class="child-content">'+
 '<span class="child-tag">&#9776; Copy '+(index+1)+'</span>'+
 '<input type="text" title="New name for this copy" value="'+h(cp.name)+'" oninput="childChange(\''+v.id+'\','+index+',\'name\',this.value)">'+
 '<select onchange="childChange(\''+v.id+'\','+index+',\'method\',this.value)">'+methodsOptions(v,cp.method)+'</select>'+
 '<select '+(v.can_scope?'':'disabled')+' onchange="childChange(\''+v.id+'\','+index+',\'scope\',this.value)">'+scopeOptions(cp.scope,v.can_scope)+'</select>'+
 '<button class="small" onclick="advancedToggle(\''+v.id+'\','+index+')">'+(state.advanced[key]?'&#9652; Less':'&#9881; Advanced')+'</button>'+
 '<button class="remove" onclick="removeCopy(\''+v.id+'\','+index+')" title="Remove this proposed copy">&#10005;</button></div>';
 if(state.advanced[key])res+='<div class="advanced"><div class="advanced-title">Copy '+(index+1)+' – individual settings (Revit-controlled parameters may be read-only)</div>'+
 '<label>Prefix <input class="extra" type="text" value="'+h(cp.prefix)+'" onchange="childChange(\''+v.id+'\','+index+',\'prefix\',this.value)"></label>'+
 '<label>Suffix <input class="extra" type="text" value="'+h(cp.suffix)+'" onchange="childChange(\''+v.id+'\','+index+',\'suffix\',this.value)"></label>'+
 '<label>View Template <select onchange="childChange(\''+v.id+'\','+index+',\'template\',this.value)">'+templateOptions(cp.template)+'</select></label>'+
 '<label>View Scale <select onchange="childChange(\''+v.id+'\','+index+',\'scale\',this.value)">'+
 viewScaleOptions(v,cp.scale)+'</select></label>'+
 '<label>Crop <select onchange="childChange(\''+v.id+'\','+index+',\'crop\',this.value)">'+option('default','Default',cp.crop)+option('on','On',cp.crop)+option('off','Off',cp.crop)+'</select></label></div>';
 return res+'</td></tr>';
}
function renderRows(){var views=visibleViews(),html='';for(var i=0;i<views.length;i++)html+=parentRow(views[i]);
 el('viewRows').innerHTML=html||'<tr><td colspan="8" class="muted" style="padding:20px">No views match the filters.</td></tr>';
 el('tableCount').innerText='('+views.length+' shown)';el('filterStats').innerText=state.views.length+' project views  ·  '+views.length+' visible';
}
function summarize(){var selected=0,copies=0,changed=0;for(var k in state.rows){if(!state.rows.hasOwnProperty(k))continue;
 var row=state.rows[k];if(!row.checked)continue;selected++;copies+=row.copies.length;
 var v=getView(k);if(v&&v.name!==row.newName)changed++;
 }return {selected:selected,copies:copies,renames:changed};}
function renderSummary(){var s=summarize();el('summaryTotals').innerText=s.selected+' selected · '+s.renames+' renames · '+s.copies+' new views';
 if(state.tab==='preview')renderPreview();}
function getRuleValue(id){return el(id).value||'';}
function createNumber(n){var val=String(n);return val.length<2?'0'+val:val;}
function ruleName(value,index){var n=String(value);var find=getRuleValue('findText');
 if(find){if(el('regexToggle')&&el('regexToggle').checked){try{n=n.replace(new RegExp(find,el('caseSensitive').checked?'g':'gi'),getRuleValue('replaceText'));}catch(err){alert('Invalid regex: '+err.message);return n;}}
 else if(el('caseSensitive').checked){n=n.split(find).join(getRuleValue('replaceText'));}
 else{var escaped=find.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');n=n.replace(new RegExp(escaped,'gi'),getRuleValue('replaceText'));}}
 n=getRuleValue('prefixText')+n+getRuleValue('suffixText');
 var c=el('caseMode').value;if(c==='upper')n=n.toUpperCase();else if(c==='lower')n=n.toLowerCase();
 else if(c==='title')n=n.replace(/\w\S*/g,function(t){return t.charAt(0).toUpperCase()+t.substr(1).toLowerCase();});
 var num=el('numberMode').value;var number=createNumber((parseInt(getRuleValue('numberStart'),10)||0)+index);
 if(num==='prefix')n=number+'_'+n;if(num==='suffix')n=n+'_'+number;return n;
}
function applyRenameRules(){var ids=sortedIds();if(!ids.length){alert('Check the source views you want to modify first.');return;}
 var idx=0;for(var k=0;k<ids.length;k++){var r=state.rows[ids[k]];
  if(el('ruleCopies').checked){for(var c=0;c<r.copies.length;c++)r.copies[c].name=ruleName(r.copies[c].baseName,idx++);}
  else {r.newName=ruleName(getView(ids[k]).name,idx++);}}
 renderRows();renderSummary();toast('Naming preview updated. Changes are not in Revit yet.');
}
function settingsSection(name){return state.tab===name;}
function tabSelect(name){state.tab=name;var tabs=document.querySelectorAll('#tabs .tab');
 for(var i=0;i<tabs.length;i++)tabs[i].className='tab'+(tabs[i].getAttribute('data-tab')===name?' active':'');
 var utility=el('secondaryTools'),tools=el('renameTools');
 tools.style.display=name==='rename'?'block':'none';utility.style.display=name==='rename'?'none':'block';
 if(name==='scope')utility.innerHTML='<div class="section-head">SCOPE BOX SETTINGS</div><span class="muted">Apply only to checked original views. Default = keep source assignment and crop.</span> '+
 '<select id="bulkScope">'+scopeOptions('default',true)+'</select> <button class="bright" onclick="applyBulkScope()">Set for Selected</button>';
 if(name==='templates')utility.innerHTML='<div class="section-head">VIEW TEMPLATE & SCALE</div><span class="muted">Configure generated copies only. Unsupported/view-template-controlled settings will be reported.</span> '+
 '<select id="bulkTemplate">'+templateOptions('default')+'</select> <select id="bulkScale">'+option('default','Default Scale','default')+option('20','1:20','default')+option('50','1:50','default')+option('100','1:100','default')+'</select> <button class="bright" onclick="applyBulkTemplate()">Set for Copies</button>';
 if(name==='health')utility.innerHTML='<div class="section-head">CLEANUP / HEALTH CHECKER</div><span class="muted">Read-only analysis. No views will be deleted or modified.</span> <button class="bright" onclick="runHealth()">Run Health Check</button>';
 if(name==='settings')utility.innerHTML='<div class="section-head">VIEWPILOT SETTINGS</div><span class="muted">Saved setups store naming rules, filter choices and copy defaults, not Revit element IDs. Use the BIM Humor toggle below.</span>';
 if(name==='preview')utility.innerHTML='<div class="section-head">CHANGE PREVIEW & CONFLICT CHECK</div><div id="previewContent"></div>';
 renderRows();renderSummary();
}
function applyBulkScope(){var val=el('bulkScope').value,ids=sortedIds();for(var i=0;i<ids.length;i++)state.rows[ids[i]].scope=val;renderRows();toast('Scope choices updated for '+ids.length+' checked original views.');}
function applyBulkTemplate(){var tpl=el('bulkTemplate').value,scale=el('bulkScale').value,ids=sortedIds();var count=0;
 for(var i=0;i<ids.length;i++){var copies=state.rows[ids[i]].copies;for(var j=0;j<copies.length;j++){copies[j].template=tpl;copies[j].scale=scale;count++;}}
 toast('Configured '+count+' proposed copies.');renderRows();
}
function computeJob(){var out=[];var ids=sortedIds();for(var i=0;i<ids.length;i++){var r=state.rows[ids[i]];
 out.push({id:ids[i],new_name:r.newName,scope:r.scope,copies:clone(r.copies)});}
 return {items:out};}
function getConflicts(job){var occupied={};var selectedSource={};var errors=[];
 for(var j=0;j<job.items.length;j++){var row=job.items[j],v=getView(row.id);if(!v)continue;
 if(row.new_name.toLowerCase()!==v.name.toLowerCase())selectedSource[v.id]=true;}
 for(var i=0;i<state.views.length;i++){var orig=state.views[i];if(!selectedSource[orig.id])occupied[orig.name.toLowerCase()]='existing view';}
 for(var k=0;k<job.items.length;k++){var r=job.items[k],source=getView(r.id);if(!source)continue;
 if(!r.new_name.trim())errors.push('Blank name for '+source.name);
 if(r.new_name.toLowerCase()!==source.name.toLowerCase())checkName(r.new_name,occupied,errors);
 for(var m=0;m<r.copies.length;m++){var cp=r.copies[m];if(!cp.name.trim())errors.push('Blank copy name for '+source.name);
 else checkName(cp.name,occupied,errors);
 if(!arrContains(source.methods,cp.method))errors.push('Unsupported duplication method: '+source.name);}
 }return errors;
}
function checkName(name,occupied,errors){var key=name.toLowerCase();if(occupied[key])errors.push('Name conflict: '+name);else occupied[key]='planned';}
function renderPreview(){var output=el('previewContent');if(!output)return;var job=computeJob(),err=getConflicts(job),s=summarize();
 var text='<div class="caption">'+s.selected+' selected source views, '+s.renames+' existing views to rename, '+s.copies+' new views to create. Changes are not applied yet.</div>';
 if(err.length){text+='<div class="status-warn"><strong>'+err.length+' issue(s) to resolve:</strong></div>';for(var j=0;j<Math.min(err.length,15);j++)text+='<div class="preview-item bad">'+h(err[j])+'</div>';}
 else{text+='<div class="status-ok">No naming conflicts found in this preview.</div>';}
 for(var i=0;i<job.items.length;i++){var r=job.items[i],v=getView(r.id);if(!v)continue;
 text+='<div class="preview-item"><strong>'+h(v.name)+'</strong> &#8594; '+h(r.new_name)+' · '+r.copies.length+' copies</div>';
 for(var k=0;k<r.copies.length;k++)text+='<div class="caption">&nbsp;&nbsp;&nbsp;'+h(r.copies[k].name)+' ('+h(METHOD_NAMES[r.copies[k].method])+')</div>';}
 output.innerHTML=text;
}
function submitChanges(){if(state.busy)return;var job=computeJob();if(!job.items.length){alert('Select at least one source view.');return;}
 var conflicts=getConflicts(job);if(conflicts.length){tabSelect('preview');alert('Resolve '+conflicts.length+' preview conflict(s) first.');return;}
 var s=summarize();if(!confirm('Apply '+s.renames+' source renames and create '+s.copies+' duplicate views in Revit?\n\nOne Revit transaction; errors roll back the batch.'))return;
 if(el('humorToggle').checked)toast(humorLines[Math.floor(Math.random()*humorLines.length)]);
 state.busy=true;host('apply',job);
}
function runHealth(){host('health',{});}
function showHealthResults(raw){var data=typeof raw==='string'?JSON.parse(raw):raw;
 state.health=data;var html='';for(var i=0;i<data.checks.length;i++){var c=data.checks[i];html+='<div class="health-item '+h(c.level)+'"><div><strong>'+h(c.title)+'</strong><b>'+h(c.count)+'</b></div>'+
 '<div class="health-detail">'+h(c.detail)+'</div>';
 if(c.examples.length)html+='<details><summary class="caption">Show examples</summary><div class="caption">'+h(c.examples.join(' · '))+'</div></details>';
 html+='</div>';}
 el('healthResults').innerHTML=html||'No issues found.';
}
function renderPresets(){var select=el('presetSelect'),html=option('','Choose a setup…','');
 for(var name in state.presets)if(state.presets.hasOwnProperty(name))html+=option(name,name,'');select.innerHTML=html;}
function setPresets(raw){state.presets=typeof raw==='string'?JSON.parse(raw):raw;renderPresets();toast('Saved setups ready.');}
function capturePreset(){var vals={};var ids=['findText','replaceText','prefixText','suffixText','caseMode','numberMode','numberStart'];
 for(var i=0;i<ids.length;i++)vals[ids[i]]=el(ids[i]).value;
 vals.caseSensitive=el('caseSensitive').checked;vals.ruleCopies=el('ruleCopies').checked;
 vals.filter=clone(state.filter);
 var selected=sortedIds();var row=selected.length?state.rows[selected[0]]:null;
 vals.defaultMethod=row?row.method:'none';vals.defaultCount=row?row.count:1;
 vals.defaultScope=row?row.scope:'default';
 return vals;}
function savePreset(){var name=prompt('Save this setup as:',el('presetSelect').value||'My ViewPilot Setup');if(!name)return;
 host('save_preset',{name:name,settings:capturePreset()});}
function loadSelectedPreset(){var key=el('presetSelect').value;if(!key||!state.presets[key])return;var v=state.presets[key];
 var ids=['findText','replaceText','prefixText','suffixText','caseMode','numberMode','numberStart'];
 for(var i=0;i<ids.length;i++)if(v[ids[i]]!==undefined)el(ids[i]).value=v[ids[i]];
 el('caseSensitive').checked=!!v.caseSensitive;el('ruleCopies').checked=!!v.ruleCopies;
 if(v.filter)state.filter=clone(v.filter);
 var ids2=sortedIds();for(var j=0;j<ids2.length;j++){
  var row=state.rows[ids2[j]],source=getView(ids2[j]);
  if(v.defaultMethod && arrContains(source.methods,v.defaultMethod)){
   row.method=v.defaultMethod;setCopiesCount(ids2[j],v.defaultCount||1,true);
  }
  if(v.defaultScope)row.scope=v.defaultScope;
 }
 renderFilters();renderRows();renderSummary();toast('Setup loaded; checked views now use saved defaults.');}
function deletePreset(){var key=el('presetSelect').value;if(!key)return;if(!confirm('Delete saved setup "'+key+'"?'))return;
 delete state.presets[key];host('delete_preset',{name:key});renderPresets();}
function saveSettings(enabled){state.settings.humor=typeof enabled==='boolean'?enabled:el('humorToggle').checked;
 syncBimHumor();host('save_settings',{humor:state.settings.humor});}
function refreshProject(){if(!confirm('Refresh all project views from Revit? Current unsaved selections and edits will be cleared.'))return;host('refresh',{});}
function windowMinimize(){host('minimize',{});}
function showHelp(){var v=el('sideHelpMessage');v.style.display=v.style.display==='none'?'block':'none';if(v.style.display==='block')v.scrollIntoView(false);}
function showApplyResults(raw){var res=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;
 var message='<p class="status-ok">Operation completed. Revit created '+res.created.length+' views and renamed '+res.renamed.length+' original views.</p>';
 if(res.created.length)message+='<p><strong>Created:</strong> '+h(res.created.join(', '))+'</p>';
 if(res.renamed.length)message+='<p><strong>Renamed:</strong> '+h(res.renamed.join(', '))+'</p>';
 if(res.warnings.length)message+='<p class="status-warn"><strong>Warnings:</strong> '+h(res.warnings.join(' | '))+'</p>';
 showModal('ViewPilot – Finished',message);
}
function hostError(raw){var data=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;showModal('ViewPilot – Could Not Apply',
 '<p class="status-warn">'+h(data.message||'Unexpected error')+'</p><p>No batch edits were committed when the transaction rolled back. See the pyRevit output for details.</p>');}
function showModal(title,html){el('modalTitle').innerText=title;el('modalMessage').innerHTML=html;el('overlay').style.display='flex';}
function hideModal(){el('overlay').style.display='none';}
var toastTimer=null;function toast(text){el('toast').innerText=text;el('toast').style.display='block';
 if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(function(){el('toast').style.display='none';},3000);}
window.onload=function(){if(!window.__inRevitHost){setHostData(demoData());el('projectName').innerHTML='<span class="status-warn">OFFLINE DEMO — launch from Revit to edit real views</span>';}};

/* ===== Production tab workflows: replaces shared secondaryTools and preview tab ===== */
var assignmentUI={scope:{selected:'',picker:false,picks:{},draft:{}},template:{selected:'',picker:false,picks:{},draft:{}}};
function setHostData(raw){
 var data=typeof raw==='string'?JSON.parse(raw):raw;
 state.views=data.views||[];state.scopes=data.scopeBoxes||[];state.templates=data.templates||[];
 state.presets=data.presets||{};state.settings=data.settings||{humor:true};state.project=data.project||'';state.version=data.version||'';state.unitSystem=data.unitSystem||'metric';
 state.rows={};state.expanded={};state.advanced={};
 for(var i=0;i<state.views.length;i++)state.rows[state.views[i].id]=newRow(state.views[i]);
 for(var j=0;j<categories.length;j++)state.filter[categories[j]]=true;
 for(var k=0;k<state.views.length;k++){
  var v=state.views[k];assignmentUI.scope.draft[v.id]=v.scope||'none';assignmentUI.template.draft[v.id]=v.template||'none';
 }
 assignmentUI.scope.picker=false;assignmentUI.template.picker=false;
 assignmentUI.scope.picks={};assignmentUI.template.picks={};
 if(!getAssignmentSource('scope',assignmentUI.scope.selected))assignmentUI.scope.selected=state.scopes.length?state.scopes[0].id:'';
 if(!getAssignmentSource('template',assignmentUI.template.selected))assignmentUI.template.selected=state.templates.length?state.templates[0].id:'';
 state.hostReady=true;state.busy=false;
 el('projectName').innerText=state.project+' · Revit '+state.version;
 el('humorToggle').checked=state.settings.humor!==false;
 setPresets(state.presets);renderFilters();renderRows();renderSummary();renderScopeList();renderTemplateList();renderAssignments('scope');renderAssignments('template');updatePending();
}
function setPresets(raw){state.presets=typeof raw==='string'?JSON.parse(raw):raw;renderPresets();}
function tabSelect(name){
 if(state.busy)return;
 state.tab=name;
 var tabs=document.querySelectorAll('#tabs .tab');for(var i=0;i<tabs.length;i++)tabs[i].className='tab'+(tabs[i].getAttribute('data-tab')===name?' active':'');
 var map={rename:'renamePage',scope:'scopePage',templates:'templatesPage',health:'healthPage',settings:'settingsPage'};
 for(var k in map)if(map.hasOwnProperty(k))el(map[k]).className='page'+(k===name?' active-page':'');
 if(name==='scope'){renderScopeList();renderAssignments('scope');}
 if(name==='templates'){renderTemplateList();renderAssignments('template');}
}
function showHelp(){host('help',{});}
function getAssignmentSource(mode,id){var items=mode==='scope'?state.scopes:state.templates;
 for(var i=0;i<items.length;i++)if(items[i].id===id)return items[i];return null;}
function pendingFor(mode){var a=assignmentUI[mode],count=0;
 for(var i=0;i<state.views.length;i++){var v=state.views[i],before=mode==='scope'?v.scope:v.template;
 if(String(a.draft[v.id])!==String(before))count++;}return count;}
function updatePending(){var s=pendingFor('scope'),t=pendingFor('template');
 el('scopeStatus').innerText=s+' pending change'+(s===1?'':'s');el('scopePending').innerText=s? s+' assignment change(s) ready to apply':'No pending scope changes';
 el('templateStatus').innerText=t+' pending change'+(t===1?'':'s');el('templatePending').innerText=t? t+' assignment change(s) ready to apply':'No pending template changes';}
function countAssigned(mode,id){var count=0,draw=assignmentUI[mode].draft;
 for(var i=0;i<state.views.length;i++)if(draw[state.views[i].id]===id && (mode!=='scope'||arrContains(['Floor Plans','Structural Plans','Area Plans'],state.views[i].category)))count++;return count;}
function renderAssignmentList(mode){var isScope=mode==='scope',items=isScope?state.scopes:state.templates;
 var a=assignmentUI[mode],search=el(isScope?'scopeSearch':'templateSearch').value.toLowerCase(),html='';
 for(var i=0;i<items.length;i++){var item=items[i];if(item.name.toLowerCase().indexOf(search)<0)continue;
  html+='<button class="assignment-card'+(item.id===a.selected?' selected-card':'')+'" onclick="chooseAssignment(\''+mode+'\',\''+h(item.id)+'\')">'+
   '<strong>'+h(item.name)+'</strong><span class="card-detail">'+countAssigned(mode,item.id)+' assigned view(s)'+
   (isScope?'':' · '+h(item.type||''))+'</span></button>';}
 el(isScope?'scopeList':'templateList').innerHTML=html||'<p class="muted">No matching project '+(isScope?'scope boxes':'view templates')+'.</p>';
 el(isScope?'scopeCount':'templateCount').innerText='('+items.length+')';
}
function renderScopeList(){renderAssignmentList('scope');}
function renderTemplateList(){renderAssignmentList('template');}
function chooseAssignment(mode,id){assignmentUI[mode].selected=id;assignmentUI[mode].picker=false;assignmentUI[mode].picks={};
 renderAssignmentList(mode);renderAssignments(mode);}
function canAssign(mode,v,target){
 if(mode==='scope')return arrContains(['Floor Plans','Structural Plans','Area Plans'],v.category)&&v.can_scope&&v.can_edit_scope;
 return arrContains(v.valid_templates||[],String(target));
}
function renderAssignments(mode){var a=assignmentUI[mode],selected=a.selected,source=getAssignmentSource(mode,selected),isScope=mode==='scope';
 el(isScope?'scopeTitle':'templateTitle').innerText=source?source.name:'Choose a '+(isScope?'scope box':'view template');
 el(isScope?'scopeAddBtn':'templateAddBtn').disabled=!source;
 var members=[],html='';for(var i=0;i<state.views.length;i++)if(a.draft[state.views[i].id]===selected && (mode!=='scope'||arrContains(['Floor Plans','Structural Plans','Area Plans'],state.views[i].category)))members.push(state.views[i]);
 if(!source)html='<div class="assignment-empty">Select an item from the left to view its assignments.</div>';
 else if(!members.length)html='<div class="assignment-empty">No views assigned. Click Select Views to add compatible views.</div>';
 else for(var j=0;j<members.length;j++){var v=members[j],editable=canAssign(mode,v,selected);
  html+='<div class="assigned-item"><div><strong>'+h(v.name)+'</strong><div class="muted">'+h(v.category)+(v.sheet?' · Sheet '+h(v.sheet):'')+'</div></div>'+
   '<button class="small"'+(editable?'':' disabled title="Not editable/compatible"')+' onclick="removeAssignment(\''+mode+'\',\''+v.id+'\')">Remove</button></div>';}
 el(isScope?'scopeAssigned':'templateAssigned').innerHTML=html;
 var picker=el(isScope?'scopePicker':'templatePicker');picker.style.display=a.picker?'flex':'none';
 if(a.picker)renderPicker(mode);
}
function togglePicker(mode){var a=assignmentUI[mode];if(!a.selected)return;
 a.picker=!a.picker;a.picks={};renderAssignments(mode);}
function eligibleForPicker(mode){var a=assignmentUI[mode],out=[];
 for(var i=0;i<state.views.length;i++){var v=state.views[i];
  if(!canAssign(mode,v,a.selected))continue;
  // Exclude all views assigned to ANY other box/template, including those staged in this session.
  if(a.draft[v.id]!=='none')continue;
  out.push(v);
 }return out;}
function renderPicker(mode){var a=assignmentUI[mode],isScope=mode==='scope',root=el(isScope?'scopePicker':'templatePicker');
 var searchId=isScope?'scopePickerSearch':'templatePickerSearch';var searchEl=el(searchId),query=searchEl?searchEl.value.toLowerCase():'';
 var rows=eligibleForPicker(mode),html='<div class="picker-title"><strong>SELECT VIEWS</strong> <input id="'+searchId+'" placeholder="Search compatible views..." onkeyup="filterPicker(\''+mode+'\')"></div>';
 html+='<div id="'+mode+'PickerChoices" class="picker-options">';var found=0;
 for(var i=0;i<rows.length;i++){var v=rows[i];if((v.name+' '+v.category).toLowerCase().indexOf(query)<0)continue;found++;
  html+='<label class="picker-option"><input type="checkbox" '+(a.picks[v.id]?'checked':'')+' onclick="pickAssignment(\''+mode+'\',\''+v.id+'\',this.checked)"> <span>'+h(v.name)+'</span> <span class="muted">'+h(v.category)+'</span></label>';}
 if(!found)html+='<div class="assignment-empty">No available compatible views. Views assigned elsewhere are intentionally hidden here.</div>';
 html+='</div><div class="picker-actions"><button onclick="togglePicker(\''+mode+'\')">Cancel</button><button class="bright" onclick="stageSelected(\''+mode+'\')">Add Selected Views</button></div>';
 root.innerHTML=html;el(searchId).value=query;
}
function filterPicker(mode){var a=assignmentUI[mode],isScope=mode==='scope',input=el(isScope?'scopePickerSearch':'templatePickerSearch');
 // Filter visible rows without rebuilding the input or losing caret position.
 var query=input.value.toLowerCase(),holder=el(mode+'PickerChoices'),labels=holder.querySelectorAll('.picker-option');
 for(var i=0;i<labels.length;i++){var text=(labels[i].innerText||labels[i].textContent||'').toLowerCase();labels[i].style.display=text.indexOf(query)>=0?'flex':'none';}}
function pickAssignment(mode,id,checked){assignmentUI[mode].picks[id]=checked;}
function stageSelected(mode){var a=assignmentUI[mode],num=0,available=eligibleForPicker(mode),valid={};
 for(var i=0;i<available.length;i++)valid[available[i].id]=true;
 for(var id in a.picks)if(a.picks.hasOwnProperty(id)&&a.picks[id]&&valid[id]){a.draft[id]=a.selected;num++;}
 a.picks={};a.picker=false;renderAssignmentList(mode);renderAssignments(mode);updatePending();
 if(!num)toast('Choose one or more compatible views using the checkboxes.');else toast(num+' view(s) added to the assignment preview.');}
function removeAssignment(mode,id){var a=assignmentUI[mode];var v=getView(id);
 if(!v||!canAssign(mode,v,a.selected))return;
 a.draft[id]='none';renderAssignmentList(mode);renderAssignments(mode);updatePending();}
function resetDraft(mode){if(!pendingFor(mode))return;if(!confirm('Discard all unapplied '+(mode==='scope'?'scope-box':'view-template')+' assignments?'))return;
 var a=assignmentUI[mode];for(var i=0;i<state.views.length;i++){var v=state.views[i];a.draft[v.id]=mode==='scope'?v.scope:v.template;}
 a.picker=false;a.picks={};renderAssignmentList(mode);renderAssignments(mode);updatePending();}
function submitAssignments(mode){if(state.busy)return;var a=assignmentUI[mode],changed=[];
 for(var i=0;i<state.views.length;i++){var v=state.views[i],before=mode==='scope'?v.scope:v.template;
  if(a.draft[v.id]!==before)changed.push({id:v.id,before:before,to:a.draft[v.id]});}
 if(!changed.length){toast('No '+(mode==='scope'?'scope-box':'view-template')+' changes to apply.');return;}
 if(!confirm('Apply '+changed.length+' '+(mode==='scope'?'scope box':'view template')+' assignment change(s) in one undoable Revit transaction?'))return;
 state.busy=true;host(mode==='scope'?'assign_scope':'assign_template',{changes:changed});}
function showAssignmentResults(raw){var data=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;
 showModal('Assignments Applied','<p class="status-ok">Successfully updated '+h(data.count)+' '+(data.mode==='scope'?'scope-box':'view-template')+' assignment(s) in Revit.</p>');}
function summarize(){var selected=0,copies=0,changed=0,scopes=0;for(var id in state.rows)if(state.rows.hasOwnProperty(id)){var r=state.rows[id];if(!r.checked)continue;selected++;copies+=r.copies.length;var v=getView(id);if(v&&v.name!==r.newName)changed++;if(r.scope!=='default')scopes++;}return{selected:selected,copies:copies,renames:changed,scopeChanges:scopes};}
function previewRename(){var job=computeJob(),issues=getConflicts(job),s=summarize(),html='<p>'+s.selected+' selected source views, '+s.renames+' renames, '+s.copies+' new views.</p>';
 if(!job.items.length)html+='<p class="status-warn">No source views selected.</p>';
 if(issues.length){html+='<h3 class="status-warn">'+issues.length+' conflict(s):</h3>';for(var i=0;i<Math.min(issues.length,25);i++)html+='<div class="preview-item bad">'+h(issues[i])+'</div>';}
 else html+='<p class="status-ok">No naming conflicts detected in local preview. Revit will validate again before committing.</p>';
 for(var j=0;j<job.items.length;j++){var r=job.items[j],v=getView(r.id);if(!v)continue;
  html+='<div class="preview-item"><strong>'+h(v.name)+'</strong> &#8594; '+h(r.new_name)+' · '+r.copies.length+' copy/copies</div>';
  for(var n=0;n<r.copies.length;n++)html+='<div class="caption">&nbsp;&nbsp; '+h(r.copies[n].name)+' ('+h(METHOD_NAMES[r.copies[n].method])+')</div>';}
 showModal('Review Changes',html);}
function showProcessing(enable){
 var p=el('processing');p.style.display=enable?'flex':'none';
 if(enable)el('processingQuote').innerText=state.settings.humor!==false?bimCurrentJoke:'';
}
function submitChanges(){if(state.busy)return;var job=computeJob();if(!job.items.length){alert('Select at least one source view.');return;}
 var issues=getConflicts(job);if(issues.length){previewRename();return;}
 var s=summarize();if(s.copies===0&&s.renames===0&&s.scopeChanges===0){toast('No view changes to apply.');return;}
 if(!confirm('Apply '+s.renames+' source renames and create '+s.copies+' views in Revit?\n\nAll changes use one undoable transaction.'))return;
 state.busy=true;
 // Show BIM humor ONLY during an actual create-views operation, and only if enabled.
 if(s.copies>0&&el('humorToggle').checked){showProcessing(true);setTimeout(function(){host('apply',job);},65);}
 else host('apply',job);
}
function showApplyResults(raw){showProcessing(false);var res=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;
 var html='<p class="status-ok">Revit created '+res.created.length+' new view(s) and renamed '+res.renamed.length+' existing view(s).</p>';
 if(res.created.length)html+='<p><strong>Created:</strong> '+h(res.created.join(', '))+'</p>';
 if(res.renamed.length)html+='<p><strong>Renamed:</strong> '+h(res.renamed.join(', '))+'</p>';
 if(res.warnings.length)html+='<p class="status-warn"><strong>Warnings:</strong> '+h(res.warnings.join(' | '))+'</p>';
 showModal('ViewPilot — Complete',html);}
function hostError(raw){showProcessing(false);var data=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;
 showModal('ViewPilot — Changes Not Applied','<p class="status-warn">'+h(data.message||'Unexpected error')+'</p><p>The failed Revit transaction was rolled back. Check the pyRevit output for details.</p>');}
function showHealthResults(raw){var data=typeof raw==='string'?JSON.parse(raw):raw;state.health=data;var html='';
 for(var i=0;i<data.checks.length;i++){var c=data.checks[i];html+='<div class="health-item '+h(c.level)+'"><div><strong>'+h(c.title)+'</strong><b>'+h(c.count)+'</b></div><div class="health-detail">'+h(c.detail)+'</div>';
  if(c.examples.length)html+='<details><summary>Show '+c.examples.length+' example(s)</summary><p class="caption">'+h(c.examples.join(' · '))+'</p></details>';html+='</div>';}
 el('healthResults').innerHTML=html||'<p class="status-ok">No findings.</p>';}
window.onload=function(){if(!window.__inRevitHost){setHostData(demoData());el('projectName').innerHTML='<span class="status-warn">OFFLINE DEMO — launch in Revit for project data</span>';}};


/* ===== ViewPilot v3: separate multi-selection dialog ===== */
var activeAssignmentMode='';
function togglePicker(mode){
 if(state.busy)return;
 if(!assignmentUI[mode] || !assignmentUI[mode].selected)return;
 activeAssignmentMode=mode;
 assignmentUI[mode].picks={};assignmentUI[mode].picker=true;
 el('assignmentDialogTitle').innerText=mode==='scope'?'Select Plan Views':'Select Views for Template';
 var selectedItem=getAssignmentSource(mode,assignmentUI[mode].selected);
 el('assignmentDialogSubtitle').innerText='Assign to '+(selectedItem?selectedItem.name:'selected item')+' — views already assigned elsewhere are excluded.';
 el('assignmentDialogSearch').value='';
 el('assignmentDialog').style.display='flex';
 renderPicker(mode);
}
function closeAssignmentPicker(){
 if(activeAssignmentMode && assignmentUI[activeAssignmentMode]){
   assignmentUI[activeAssignmentMode].picker=false;
   assignmentUI[activeAssignmentMode].picks={};
 }
 activeAssignmentMode='';
 el('assignmentDialog').style.display='none';
}
function renderPicker(mode){
 if(!assignmentUI[mode] || !assignmentUI[mode].picker)return;
 activeAssignmentMode=mode;
 var items=eligibleForPicker(mode),html='';
 for(var i=0;i<items.length;i++){
   var v=items[i];html+='<label class="assignment-dialog-row"><input data-vid="'+h(v.id)+'" type="checkbox" '+(assignmentUI[mode].picks[v.id]?'checked':'')+' onclick="pickAssignment(\''+mode+'\',\''+v.id+'\',this.checked)"><span class="assignment-view-name">'+h(v.name)+'</span><span class="muted">'+h(v.category)+'</span></label>';
 }
 if(!items.length)html='<div class="assignment-empty">No unassigned compatible views are available.</div>';
 el('assignmentDialogList').innerHTML=html;
 el('assignmentDialogCount').innerText=items.length+' available views';
 filterPicker();
}
function filterPicker(){
 var query=el('assignmentDialogSearch').value.toLowerCase();
 var items=el('assignmentDialogList').querySelectorAll('.assignment-dialog-row');var count=0;
 for(var i=0;i<items.length;i++){
  var name=(items[i].innerText||items[i].textContent||'').toLowerCase();
  var show=!query||name.indexOf(query)!==-1;
  items[i].style.display=show?'flex':'none';if(show)count++;
 }
 el('assignmentDialogCount').innerText=count+' shown / '+items.length+' available';
}
function pickAllAvailable(flag){
 if(!activeAssignmentMode)return;
 var checkboxes=el('assignmentDialogList').querySelectorAll('.assignment-dialog-row');
 for(var i=0;i<checkboxes.length;i++){
  if(checkboxes[i].style.display==='none')continue;
  var box=checkboxes[i].getElementsByTagName('input')[0];
  box.checked=flag;var vId=box.getAttribute('data-vid');
  if(!vId){var mode=activeAssignmentMode,items=eligibleForPicker(mode);var all=el('assignmentDialogList').querySelectorAll('.assignment-dialog-row');
   for(var k=0;k<all.length;k++)if(all[k]===checkboxes[i]){vId=items[k].id;break;}}
  if(vId)assignmentUI[activeAssignmentMode].picks[vId]=flag;
 }
}
function stageSelectedFromDialog(){
 if(!activeAssignmentMode)return;
 var mode=activeAssignmentMode;
 var a=assignmentUI[mode],allowed=eligibleForPicker(mode),eligible={};var count=0;
 for(var i=0;i<allowed.length;i++)eligible[allowed[i].id]=true;
 for(var key in a.picks)if(a.picks.hasOwnProperty(key)&&a.picks[key]&&eligible[key]){
  a.draft[key]=a.selected;count++;
 }
 if(!count){toast('Select at least one compatible view using checkboxes.');return;}
 closeAssignmentPicker();
 renderAssignmentList(mode);renderAssignments(mode);updatePending();
 toast(count+' view(s) added. Click Apply Changes to update Revit.');
}

/* ===== v3: persistent tab-aware Apply bar (never hidden by table scroll) ===== */
function updateGlobalApply(){
 var active=state.tab;
 var labels={rename:['RENAME & DUPLICATE','Apply pending view name changes and created copies'],
             scope:['SCOPE BOXES','Apply selected scope-box assignments'],
             templates:['VIEW TEMPLATES','Apply selected view-template assignments']};
 var bar=el('globalApplyBar');if(!bar)return;
 if(!labels[active]){bar.style.display='none';return;}
 bar.style.display='flex';
 el('globalApplyTitle').innerText=labels[active][0];
 el('globalApplyHint').innerText=labels[active][1];
 el('globalApplyButton').innerText=active==='rename'?'▶ Apply Changes':active==='scope'?'▶ Apply Scope Changes':'▶ Apply Template Changes';
 el('globalReviewButton').style.display=active==='rename'?'inline-block':'none';
}
function applyCurrentWorkspace(){
 if(state.tab==='rename')return submitChanges();
 if(state.tab==='scope')return submitAssignments('scope');
 if(state.tab==='templates')return submitAssignments('template');
}
/* Keep the existing handlers; update the fixed bar when switching tabs. */
var originalTabSelect=tabSelect;
tabSelect=function(name){originalTabSelect(name);updateGlobalApply();};
var originalSetHostData=setHostData;
setHostData=function(raw){originalSetHostData(raw);updateGlobalApply();};

/* ===== NdevTools ViewPilot v4 - approved behavior updates =====
   ES5 for embedded .NET WebBrowser. All model writes are sent to pyRevit only
   after Apply confirmation; this UI never calls an external service. */
function getTemplateData(id){for(var i=0;i<state.templates.length;i++)if(String(state.templates[i].id)===String(id))return state.templates[i];return null;}
function entityName(items,id){for(var i=0;i<items.length;i++)if(String(items[i].id)===String(id))return items[i].name;return id==='none'?'None':'Unassigned';}
function selectedCommon(id){var e=el(id);return e?e.value:'default';}
function commonMethod(){return selectedCommon('commonMethod')||'duplicate';}
function newRow(v){return {checked:false,newName:v.name,method:'none',count:0,scope:'default',copies:[]};}
function newCopy(v,index,method){
 var name=v.name+' - '+('0'+(index+1)).slice(-2),cp={baseName:name,name:name,manual:false,
 method:method||'duplicate',scope:selectedCommon('commonScope'),template:selectedCommon('commonTemplate'),
 scale:selectedCommon('commonScale')};
 if(!arrContains(v.methods,cp.method))cp.method=v.methods.length?v.methods[0]:'none';
 if(cp.template!=='default'&&cp.template!=='none'&&!arrContains(v.valid_templates||[],cp.template))cp.template='default';
 if(cp.method==='dependent'){cp.template='default';cp.scale='default';}
 else if(cp.template!=='default'&&cp.template!=='none'){
  var selectedTemplate=getTemplateData(cp.template);
  if(selectedTemplate&&!selectedTemplate.controls_scale&&cp.scale==='default')cp.scale='ask';
 }
 return cp;
}
function cpTemplate(v,cp){return cp.template==='default'?v.template:cp.template;}
function scalePolicy(v,cp){
 if(cp.method==='dependent')return {disabled:true,label:'Inherits parent view scale',reason:'Dependent copies inherit the parent view template and scale.'};
 var tid=cpTemplate(v,cp),tpl=getTemplateData(tid);
 if(tpl&&tpl.controls_scale){
  return {disabled:true,label:'Template: '+formatScale(tpl.scale),reason:'View Scale is automatically fetched from the selected View Template.'};
 }
 if(tpl&&cp.template!=='default')return {disabled:false,label:'Select a view scale',reason:'The selected View Template does not control View Scale. Please select a scale.'};
 return {disabled:false,label:'Default (source: '+formatScale(v.scale)+')',reason:'Scale can be set manually when not controlled by a template.'};
}
function formatScale(scale){return state.unitSystem==='imperial'?imperialScaleLabel(Number(scale)||0):'1:'+(Number(scale)||0);}
function copyTemplateOptions(view,selected){var html=option('default','Default (source)',selected)+option('none','None',selected);
 for(var i=0;i<state.templates.length;i++){
  var t=state.templates[i];if(arrContains(view.valid_templates||[],t.id)||String(view.template)===String(t.id))html+=option(t.id,t.name,selected);
 }return html;
}
function copyMethodOptions(v,sel){var html='';for(var i=0;i<v.methods.length;i++)html+=option(v.methods[i],METHOD_NAMES[v.methods[i]],sel);return html;}
function methodText(v,cp){if(!v.methods.length)return 'Not supported';return cp?METHOD_NAMES[cp.method]:METHOD_NAMES[commonMethod()];}
function setCopiesCount(id,value,skipRender){
 var r=state.rows[id],v=getView(id),n=parseInt(value,10);if(isNaN(n)||n<0)n=0;if(n>100)n=100;
 if(n&&!v.methods.length){toast('This view does not support duplication in Revit.');n=0;}
 r.count=n;r.method=n?commonMethod():'none';
 while(r.copies.length<n)r.copies.push(newCopy(v,r.copies.length,commonMethod()));
 while(r.copies.length>n)r.copies.pop();
 if(n){r.checked=true;state.expanded[id]=true;}
 if(!skipRender){renderRows();renderSummary();}
}
function selectView(id,checked){state.rows[id].checked=checked;renderRows();renderSummary();}
function checkVisible(val){var views=visibleViews();for(var i=0;i<views.length;i++)state.rows[views[i].id].checked=val;renderRows();renderSummary();}
function changeMethod(id,method){/* Parent method is centrally controlled in v4. */}
function childChange(id,idx,key,value){
 var cp=state.rows[id].copies[idx],v=getView(id);if(!cp)return;
 cp[key]=value;if(key==='name')cp.manual=true;
 if(key==='method'){
  if(!arrContains(v.methods,value)){cp.method=v.methods.length?v.methods[0]:'none';}
  // Dependent copies inherit template + scale. Keep prior selections only if
  // explicitly changing back; no invalid template/scale writes for dependent.
  if(cp.method==='dependent'){cp.template='default';cp.scale='default';}
  renderRows();
 }else if(key==='template'){
  var policy=scalePolicy(v,cp);if(policy.disabled)cp.scale='default';
  else if(value!=='default'&&value!=='none'&&getTemplateData(value))cp.scale='ask';
  renderRows();
 }
 renderSummary();
}
function parentRow(v){var r=state.rows[v.id],count=r.copies.length;
 var expand=count?'<span class="expander" onclick="expandRow(\''+h(v.id)+'\')">'+(state.expanded[v.id]?'&#9662;':'&#9656;')+'</span>':'';
 var summary='N/A';
 if(v.methods.length){
  summary=arrContains(v.methods,commonMethod())?METHOD_NAMES[commonMethod()]:'Common method unsupported';
  if(count){summary=METHOD_NAMES[r.copies[0].method];
   for(var si=1;si<r.copies.length;si++)if(r.copies[si].method!==r.copies[0].method){summary='Mixed methods';break;}
   summary+=' · '+count+' copies';}
 }
 var html='<tr class="parent'+(r.checked?' selected':'')+'">'+
 '<td class="checkcol"><input type="checkbox" '+(r.checked?'checked':'')+' onclick="selectView(\''+h(v.id)+'\',this.checked)"></td>'+
 '<td>'+expand+h(v.category)+(v.sheet?'<div class="muted tiny">Sheet '+h(v.sheet)+'</div>':'')+'</td>'+
 '<td>'+h(v.name)+'</td>'+
 '<td><input type="text" title="Rename this existing view" value="'+h(r.newName)+'" oninput="changeOriginalName(\''+h(v.id)+'\',this.value)"></td>'+
 '<td><span class="method-summary">'+h(summary)+'</span></td>'+
 '<td><input type="number" min="0" max="100" value="'+h(r.count)+'" '+(!v.methods.length?'disabled':'')+' onchange="setCopiesCount(\''+h(v.id)+'\',this.value)" title="Set number of new copies; 0 means rename only"></td>'+
 '<td><select '+(v.can_scope?'':'disabled')+' onchange="changeParentScope(\''+h(v.id)+'\',this.value)">'+scopeOptions(r.scope,v.can_scope)+'</select></td>'+
 '<td>'+(r.checked?'<span class="status-info">'+(count?'+'+count+' views':'Selected')+'</span>':'<span class="muted">—</span>')+'</td></tr>';
 if(count&&state.expanded[v.id])for(var i=0;i<count;i++)html+=childRows(v,i,r.copies[i]);
 return html;
}
function childRows(v,index,cp){var key=v.id+':'+index,expanded=!!state.advanced[key],policy=scalePolicy(v,cp),modeDependent=cp.method==='dependent';
 var method=copyMethodOptions(v,cp.method),tpl=modeDependent?option('default','Inherit parent template','default'):copyTemplateOptions(v,cp.template);
 var scale=policy.disabled?option('default',policy.label,'default'):viewScaleOptions(v,cp.scale);
 if(!policy.disabled&&cp.scale==='ask')scale=option('ask','Select a scale…','ask')+scale;
 var result='<tr class="child"><td></td><td colspan="7"><div class="child-content">'+
 '<span class="child-tag">&#9776; Copy '+(index+1)+'</span>'+
 '<input type="text" title="Edit full name directly" value="'+h(cp.name)+'" oninput="childChange(\''+h(v.id)+'\','+index+',\'name\',this.value)">'+
 '<select title="Duplication method for this copy" onchange="childChange(\''+h(v.id)+'\','+index+',\'method\',this.value)">'+method+'</select>'+
 '<button class="small" onclick="advancedToggle(\''+h(v.id)+'\','+index+')">'+(expanded?'&#9652; Hide settings':'&#9881; Copy settings')+'</button>'+
 '<button class="remove" onclick="removeCopy(\''+h(v.id)+'\','+index+')" title="Remove proposed copy">&#10005;</button></div>';
 if(expanded)result+='<div class="advanced"><div class="advanced-title">Copy '+(index+1)+' · '+h(METHOD_NAMES[cp.method])+' · Individual settings</div>'+
 '<label>View Template<select '+(modeDependent?'disabled':'')+' onchange="childChange(\''+h(v.id)+'\','+index+',\'template\',this.value)">'+tpl+'</select></label>'+
 '<label>View Scale<select '+(policy.disabled?'disabled':'')+' onchange="childChange(\''+h(v.id)+'\','+index+',\'scale\',this.value)">'+scale+'</select></label>'+
 '<label>Scope Box<select '+(v.can_scope?'':'disabled')+' onchange="childChange(\''+h(v.id)+'\','+index+',\'scope\',this.value)">'+scopeOptions(cp.scope,v.can_scope)+'</select></label>'+
 '<div class="common-hint" style="width:100%">'+h(policy.reason)+'</div></div>';
 return result+'</td></tr>';
}
function initCommon(){
 var cs=el('commonScope'),ct=el('commonTemplate'),cm=el('commonMethod');if(!cs||!ct||!cm)return;
 var oldScope=cs.value||'default',oldTemplate=ct.value||'default',oldMethod=cm.value||'duplicate';
 cs.innerHTML=scopeOptions(oldScope,true);
 ct.innerHTML=templateOptions(oldTemplate);
 cm.value=oldMethod;
 updateCommonControls();
}
function updateCommonControls(){var method=commonMethod(),template=selectedCommon('commonTemplate'),t=getTemplateData(template),dependent=method==='dependent';
 el('commonTemplate').disabled=dependent;el('commonScale').disabled=dependent||!!(t&&t.controls_scale);
 var selected=selectedCommon('commonScale'),scaleOptions='';
 if(dependent)scaleOptions=option('default','Inherits parent scale','default');
 else if(t&&t.controls_scale)scaleOptions=option('default','Template: '+formatScale(t.scale),'default');
 else {
  scaleOptions=t&&!t.controls_scale?option('ask','Select a view scale…',selected):option('default','Default (source)',selected);
  var fake={scale:0};scaleOptions+=viewScaleOptions(fake,selected).replace(/<option[^>]*value="default"[^>]*>[^<]*<\/option>/,'');
 }
 el('commonScale').innerHTML=scaleOptions;
 // Existing per-copy overrides are never silently overwritten; use the
 // explicit Apply to Checked Copies button for that operation.
 var hint=dependent?'Dependent copies inherit View Template and View Scale from their parent.':
 (t&&t.controls_scale?'View Scale is automatically fetched from the selected View Template.':
 (t?'The selected View Template does not control View Scale. Please select a scale.':'Common settings are defaults for new copies. Edit each copy independently.'));
 el('commonHint').innerText=hint;
 renderRows();renderSummary();
}
function applyCommonToSelection(){var ids=sortedIds(),changes=0,skipped=0,method=commonMethod(),tpl=selectedCommon('commonTemplate'),scope=selectedCommon('commonScope'),scale=selectedCommon('commonScale');
 if(!ids.length){toast('Select source views using their checkboxes first.');return;}
 for(var i=0;i<ids.length;i++){var v=getView(ids[i]),r=state.rows[ids[i]];
  if(!r.copies.length)continue;
  for(var j=0;j<r.copies.length;j++){
   var cp=r.copies[j];if(arrContains(v.methods,method))cp.method=method;else skipped++;
   cp.scope=scope;
   if(cp.method==='dependent'){cp.template='default';cp.scale='default';}
   else{
    cp.template=(tpl==='default'||tpl==='none'||arrContains(v.valid_templates||[],tpl))?tpl:'default';
    if(cp.template!==tpl)skipped++;
    var tmpl=getTemplateData(cp.template);
    cp.scale=(tmpl&&!tmpl.controls_scale&&scale==='default')?'ask':scale;
   }
   changes++;
  }
 }
 renderRows();renderSummary();toast(changes+' copy settings updated.'+(skipped?' '+skipped+' incompatible setting(s) retained their source defaults.':''));
}
function getConflicts(job){var occupied={},selectedSource={},errors=[];
 for(var j=0;j<job.items.length;j++){var row=job.items[j],v=getView(row.id);if(v&&row.new_name.toLowerCase()!==v.name.toLowerCase())selectedSource[v.id]=true;}
 for(var i=0;i<state.views.length;i++){var orig=state.views[i];if(!selectedSource[orig.id])occupied[orig.name.toLowerCase()]='existing view';}
 for(var k=0;k<job.items.length;k++){var r=job.items[k],source=getView(r.id);if(!source)continue;
  if(!r.new_name.replace(/^\s+|\s+$/g,''))errors.push('Blank original view name for '+source.name);
  if(r.new_name.toLowerCase()!==source.name.toLowerCase())checkName(r.new_name,occupied,errors);
  for(var m=0;m<r.copies.length;m++){
   var cp=r.copies[m];if(!cp.name.replace(/^\s+|\s+$/g,''))errors.push('Blank copy name for '+source.name);else checkName(cp.name,occupied,errors);
   if(!arrContains(source.methods,cp.method))errors.push('Unsupported '+cp.method+' for '+source.name);
   if(cp.method!=='dependent'){
    var tid=cpTemplate(source,cp),template=getTemplateData(tid);
    if(cp.template!=='default'&&cp.template!=='none'&&!arrContains(source.valid_templates||[],cp.template))errors.push('Incompatible template on '+cp.name);
    if(template&&!template.controls_scale&&cp.scale==='ask')errors.push('Select view scale on '+cp.name);
   }
  }
 }return errors;
}
function renderSummary(){var s=summarize(),summary=s.selected+' selected · '+s.renames+' renames · '+s.copies+' new '+(s.copies===1?'view':'views');
 if(el('summaryTotals'))el('summaryTotals').innerText=summary;
 if(state.tab==='rename'&&el('globalApplyHint'))el('globalApplyHint').innerText=summary;
}
function updatePending(){var s=pendingFor('scope'),t=pendingFor('template');
 if(el('scopeStatus'))el('scopeStatus').innerText=s+' pending change'+(s===1?'':'s');
 if(el('templateStatus'))el('templateStatus').innerText=t+' pending change'+(t===1?'':'s');
 if(el('scopePending'))el('scopePending').innerText=s?s+' changes':'No pending changes';
 if(el('templatePending'))el('templatePending').innerText=t?t+' changes':'No pending changes';
 updateGlobalApply();
}
function updateGlobalApply(){var bar=el('globalApplyBar');if(!bar)return;
 var mode=state.tab,available=mode==='rename'||mode==='scope'||mode==='templates';bar.style.display=available?'flex':'none';if(!available)return;
 var titles={rename:'RENAME & DUPLICATE',scope:'SCOPE BOXES',templates:'VIEW TEMPLATES'};
 el('globalApplyTitle').innerText=titles[mode];
 el('globalApplyHint').innerText=mode==='rename'?(function(){var s=summarize();return s.selected+' selected · '+s.renames+' renames · '+s.copies+' new '+(s.copies===1?'view':'views');})():
 pendingFor(mode==='scope'?'scope':'template')+' pending assignments';
 el('globalReviewButton').style.display=mode==='rename'?'inline-block':'none';
 el('globalApplyButton').innerText=mode==='scope'?'▶ Apply Scope Changes':mode==='templates'?'▶ Apply Template Changes':'▶ Apply Changes';
}
function tabSelect(name){if(state.busy)return;
 state.tab=name;
 var tabs=document.querySelectorAll('#tabs .tab');for(var i=0;i<tabs.length;i++)tabs[i].className='tab'+(tabs[i].getAttribute('data-tab')===name?' active':'');
 var map={rename:'renamePage',scope:'scopePage',templates:'templatesPage',health:'healthPage',settings:'settingsPage'};
 for(var k in map)if(map.hasOwnProperty(k))el(map[k]).className='page'+(k===name?' active-page':'');
 if(name==='scope'){renderScopeList();renderAssignments('scope');}
 if(name==='templates'){renderTemplateList();renderAssignments('template');}
 updateGlobalApply();
}
function canAssign(mode,v,target){
 if(mode==='scope')return arrContains(['Floor Plans','Structural Plans','Area Plans'],v.category)&&!!v.can_scope&&!!v.can_edit_scope;
 // Both the API-supported list and the current assignment matter; assigned
 // templates must not disappear from the selection dialog.
 return arrContains(v.valid_templates||[],String(target))||String(v.template)===String(target);
}
function eligibleForPicker(mode){var a=assignmentUI[mode],out=[];
 for(var i=0;i<state.views.length;i++){var v=state.views[i];if(canAssign(mode,v,a.selected))out.push(v);}
 return out;
}
function togglePicker(mode){if(state.busy||!assignmentUI[mode]||!assignmentUI[mode].selected)return;
 activeAssignmentMode=mode;var a=assignmentUI[mode];a.picker=true;a.picks={};
 for(var i=0;i<state.views.length;i++){var v=state.views[i];if(a.draft[v.id]===a.selected)a.picks[v.id]=true;}
 var source=getAssignmentSource(mode,a.selected);
 el('assignmentDialogTitle').innerText=mode==='scope'?'Select Plan Views':'Select Views for Template';
 el('assignmentDialogSubtitle').innerText='Assign to '+(source?source.name:'selected item')+' · Current assignments are shown on each view.';
 el('assignmentDialogSearch').value='';el('assignmentDialog').style.display='flex';renderPicker(mode);
}
function renderPicker(mode){if(!assignmentUI[mode]||!assignmentUI[mode].picker)return;
 var a=assignmentUI[mode],items=eligibleForPicker(mode),html='';activeAssignmentMode=mode;
 for(var i=0;i<items.length;i++){
  var v=items[i],current=a.draft[v.id]||'none',selected=current===a.selected;
  var sourceName=mode==='scope'?entityName(state.scopes,current):entityName(state.templates,current);
  var original=mode==='scope'?(v.scope||'none'):(v.template||'none');
  var originalName=mode==='scope'?entityName(state.scopes,original):entityName(state.templates,original);
  var label=current==='none'?'Unassigned':(selected?'Already assigned: ':'Current: ')+sourceName;
  if(current!==original)label='Current Revit: '+originalName+' · Pending: '+sourceName;
  html+='<label class="assignment-dialog-row'+(selected?' already':'')+'"><input data-vid="'+h(v.id)+'" type="checkbox" '+(a.picks[v.id]?'checked':'')+
  ' onclick="pickAssignment(\''+h(mode)+'\',\''+h(v.id)+'\',this.checked)"><span class="assignment-view-name">'+h(v.name)+'</span><span class="muted">'+h(v.category)+'</span><span class="current-assignment">'+h(label)+'</span></label>';
 }
 if(!items.length)html='<div class="assignment-empty">No compatible views are available for this selection. Check the project view type and API compatibility.</div>';
 el('assignmentDialogList').innerHTML=html;el('assignmentDialogCount').innerText=items.length+' compatible views';filterPicker();
}
function stageSelectedFromDialog(){if(!activeAssignmentMode)return;
 var mode=activeAssignmentMode,a=assignmentUI[mode],allowed=eligibleForPicker(mode),changed=0;
 for(var i=0;i<allowed.length;i++){
  var id=allowed[i].id,checked=!!a.picks[id],prev=a.draft[id]||'none';
  if(checked&&prev!==a.selected){a.draft[id]=a.selected;changed++;}
  else if(!checked&&prev===a.selected){a.draft[id]='none';changed++;}
 }
 closeAssignmentPicker();renderAssignmentList(mode);renderAssignments(mode);updatePending();
 toast(changed+' view assignment(s) staged. Click Apply to save changes in Revit.');
}
function pickAllAvailable(flag){if(!activeAssignmentMode)return;
 var inputs=el('assignmentDialogList').getElementsByTagName('input');for(var i=0;i<inputs.length;i++){
  var e=inputs[i],row=e.parentNode;if(row.style.display==='none'||e.disabled)continue;
  e.checked=flag;assignmentUI[activeAssignmentMode].picks[e.getAttribute('data-vid')]=flag;
 }
}
function showHealthResults(raw){var data=typeof raw==='string'?JSON.parse(raw):raw;state.health=data;
 var html='<h3 class="health-heading">Potential Errors &amp; Review Items</h3>';
 for(var i=0;i<(data.checks||[]).length;i++){
  var c=data.checks[i],examples=c.examples||[];
  html+='<div class="health-item '+h(c.level)+'"><button class="health-item-header" onclick="toggleHealthGroup('+i+')"><strong>'+
  h(c.title)+'</strong><b>'+h(c.count)+'</b><span id="healthArrow'+i+'">&#9662;</span></button>'+
  '<div class="health-detail">'+h(c.detail)+'</div><div class="health-view-list" id="healthGroup'+i+'">';
  if(!examples.length)html+='<div class="health-view-row muted">No affected views found.</div>';
  for(var j=0;j<examples.length;j++)html+='<div class="health-view-row">'+h(examples[j])+'</div>';
  html+='</div></div>';
 }
 el('healthResults').innerHTML=html;
}
function toggleHealthGroup(i){var g=el('healthGroup'+i),arrow=el('healthArrow'+i);if(!g)return;
 g.style.display=g.style.display==='none'?'block':'none';arrow.innerHTML=g.style.display==='none'?'&#9656;':'&#9662;';
}
function capturePreset(){var obj={},ids=['findText','replaceText','prefixText','suffixText','caseMode','numberMode','numberStart'];
 for(var i=0;i<ids.length;i++)obj[ids[i]]=el(ids[i]).value;
 obj.caseSensitive=el('caseSensitive').checked;obj.ruleCopies=el('ruleCopies').checked;obj.regexToggle=el('regexToggle').checked;
 obj.filter=clone(state.filter);obj.commonMethod=commonMethod();obj.commonTemplate=selectedCommon('commonTemplate');
 obj.commonScope=selectedCommon('commonScope');obj.commonScale=selectedCommon('commonScale');
 var selected=sortedIds();obj.defaultCount=selected.length?state.rows[selected[0]].count:0;
 return obj;
}
function loadSelectedPreset(){var key=el('presetSelect').value;if(!key||!state.presets[key])return;
 var v=state.presets[key],ids=['findText','replaceText','prefixText','suffixText','caseMode','numberMode','numberStart'];
 for(var i=0;i<ids.length;i++)if(v[ids[i]]!==undefined)el(ids[i]).value=v[ids[i]];
 el('caseSensitive').checked=!!v.caseSensitive;el('ruleCopies').checked=!!v.ruleCopies;el('regexToggle').checked=!!v.regexToggle;
 if(v.filter)state.filter=clone(v.filter);
 if(v.commonMethod)el('commonMethod').value=v.commonMethod;
 if(v.commonTemplate)el('commonTemplate').value=v.commonTemplate;
 if(v.commonScope)el('commonScope').value=v.commonScope;
 updateCommonControls();
 if(v.commonScale)el('commonScale').value=v.commonScale;
 var ids2=sortedIds();for(var j=0;j<ids2.length;j++)if(v.defaultCount>0)setCopiesCount(ids2[j],v.defaultCount,true);
 renderFilters();renderRows();renderSummary();toast('Saved setup loaded into Common Settings.');
}
/* v3's setHostData initializes view filters, project assignments and rendering.
   Extend it after data is available so source and template lists stay fresh. */
var v3SetHostData=setHostData;
setHostData=function(raw){v3SetHostData(raw);initCommon();updateGlobalApply();};
/* ===== ViewPilot v5 — approved corrections. ES5; offline/WinForms WebBrowser safe. ===== */
var v5ReviewFlags={},v5ReviewInitialized=false,v5BeforeCommon={},v5WasCommonOn=false;
function v5On(id){var p=el(id);return !!(p&&p.checked);}
function v5LockNotice(){showModal('Individual Duplication Disabled','<p>Turn off <b>Common Duplication Method</b> to configure individual duplication methods and copy counts.</p>');}
function v5AllowedSource(v){return v&&v.methods&&arrContains(v.methods,commonMethod());}
function v5SetOne(id){var v=getView(id),r=state.rows[id];if(!v5AllowedSource(v))return false;
 if(r.count>1&&!v5BeforeCommon.hasOwnProperty(id))v5BeforeCommon[id]=r.count;
 v4SetCopiesCount(id,1,true);r.count=1;r.method=commonMethod();
 if(r.copies.length){r.copies[0].method=commonMethod();if(commonMethod()==='dependent'){r.copies[0].template='default';r.copies[0].scale='default';}}
 return true;
}
var v4SetCopiesCount=setCopiesCount;
setCopiesCount=function(id,count,skipRender){if(v5On('commonMethodOn')&&state.rows[id]&&state.rows[id].checked){
 v5SetOne(id);if(!skipRender){renderRows();renderSummary();v5LockNotice();}return;
 }v4SetCopiesCount(id,count,true);v5ReviewInitialized=false;if(!skipRender){renderRows();renderSummary();}};
var v4SelectView=selectView;
selectView=function(id,checked){state.rows[id].checked=checked;if(checked&&v5On('commonMethodOn')){if(!v5SetOne(id))toast('The common duplication method is unsupported by this view.');}
 renderRows();renderSummary();v5ReviewInitialized=false;};
var v4CheckVisible=checkVisible;
checkVisible=function(checked){var views=visibleViews();for(var i=0;i<views.length;i++){
 var id=views[i].id;state.rows[id].checked=checked;
 if(checked&&v5On('commonMethodOn'))v5SetOne(id);
 }renderRows();renderSummary();v5ReviewInitialized=false;};
var v4ChildChange=childChange;
childChange=function(id,idx,key,value){if(key==='method'&&v5On('commonMethodOn')){v5LockNotice();renderRows();return;}
 v4ChildChange(id,idx,key,value);
 var cp=state.rows[id].copies[idx];if(key==='scope')cp.v5CommonScopeApplied=false;
 if(key==='template')cp.v5CommonTemplateApplied=false;
 if(key==='scale')cp.v5CommonScaleApplied=false;
 v5ReviewInitialized=false;};
var v4RemoveCopy=removeCopy;
removeCopy=function(id,idx){if(v5On('commonMethodOn')){v5LockNotice();return;}
 v4RemoveCopy(id,idx);v5ReviewInitialized=false;};
var v4ChangeOriginalName=changeOriginalName;
changeOriginalName=function(id,value){v4ChangeOriginalName(id,value);v5ReviewInitialized=false;};
function v5ToggleCommon(){
 var common=v5On('commonMethodOn');
 if(common&&!v5WasCommonOn){var multiple=[];var ids=sortedIds();for(var i=0;i<ids.length;i++){
  var r=state.rows[ids[i]];if(r.count>1)multiple.push(getView(ids[i]).name+' ('+r.count+')');
  v5BeforeCommon[ids[i]]=r.count;
 }
 if(multiple.length&&!confirm('Common Duplication Method will replace these individual copy counts with 1:\n'+multiple.join('\n')+'\n\nContinue?')){
  el('commonMethodOn').checked=false;return;
 }
 }
 v5WasCommonOn=common;
 var names=['Scope','Template','Method','Scale'];for(var j=0;j<names.length;j++){
  var name=names[j],select=el('common'+name),chk=el('common'+name+'On');
  if(select)select.disabled=!chk.checked;
 }
 if(common){var ids=sortedIds(),skips=0;for(var k=0;k<ids.length;k++)if(!v5SetOne(ids[k]))skips++;
 if(skips)toast(skips+' selected view(s) cannot use this duplication method.');
 }else if(v5BeforeCommon){ // On unlock the user can again set any copy count; keep current one until edited.
  v5BeforeCommon={};
 }
 v5CommonChanged(false);
}
function v5CommonChanged(toggleOnly){
 var method=commonMethod(),tpl=selectedCommon('commonTemplate'),t=getTemplateData(tpl),isDep=v5On('commonMethodOn')&&method==='dependent';
 // Do not make checked State invisible; disabled means unavailable due to inheritance.
 el('commonScope').disabled=!v5On('commonScopeOn');
 el('commonMethod').disabled=!v5On('commonMethodOn');
 el('commonTemplate').disabled=!v5On('commonTemplateOn')||isDep;
 var existingScale=selectedCommon('commonScale');
 // v4 preserves the v4 template-scale policy and reconstructs scale options.
 updateCommonControls();
 if(el('commonScale').querySelector('option[value="'+existingScale+'"]'))el('commonScale').value=existingScale;
 el('commonScale').disabled=!v5On('commonScaleOn')||isDep||!!(v5On('commonTemplateOn')&&t&&t.controls_scale);
 el('commonHint').innerText=isDep?'Dependent copies inherit their parent template and scale.':
   (v5On('commonTemplateOn')&&t&&t.controls_scale?'View Scale fetched from the selected View Template: '+formatScale(t.scale):
   'Checked common settings apply only to NEW copies. Original views stay unchanged.');
 if(v5On('commonMethodOn')){var ids=sortedIds();for(var i=0;i<ids.length;i++)v5SetOne(ids[i]);}
 if(!toggleOnly)v5ApplyCommonCore(true);
 renderRows();renderSummary();v5ReviewInitialized=false;updateCopiesResetControls();
}
function v5ApplyCommonCore(quiet){var ids=sortedIds(),changes=0,skipped=0;
 if(!ids.length){if(!quiet)toast('Check one or more source views.');return;}
 var tpl=selectedCommon('commonTemplate'),scope=selectedCommon('commonScope'),scale=selectedCommon('commonScale'),method=commonMethod();
 for(var i=0;i<ids.length;i++){var v=getView(ids[i]),r=state.rows[ids[i]];
  if(v5On('commonScopeOn')&&v.can_scope)r.scope=scope;
  else if(!v5On('commonScopeOn')&&r.v5CommonScopeApplied)r.scope='default';
  r.v5CommonScopeApplied=v5On('commonScopeOn')&&v.can_scope;
  if(v5On('commonMethodOn'))v5SetOne(ids[i]);
  for(var j=0;j<r.copies.length;j++){
   var cp=r.copies[j];
   if(v5On('commonMethodOn')){if(!arrContains(v.methods,method)){skipped++;continue;}cp.method=method;}
   if(v5On('commonScopeOn')){if(v.can_scope){cp.scope=scope;cp.v5CommonScopeApplied=true;}else skipped++;}
   else if(cp.v5CommonScopeApplied){cp.scope='default';cp.v5CommonScopeApplied=false;}
   if(cp.method==='dependent'){cp.template='default';cp.scale='default';continue;}
   if(v5On('commonTemplateOn')){
    if(tpl==='default'||tpl==='none'||arrContains(v.valid_templates||[],tpl)){cp.template=tpl;cp.v5CommonTemplateApplied=true;}
    else{skipped++;}
   }
   else if(cp.v5CommonTemplateApplied){cp.template='default';cp.v5CommonTemplateApplied=false;}
   if(v5On('commonScaleOn')){
    var templateId=cpTemplate(v,cp),t=getTemplateData(templateId);
    if(t&&t.controls_scale)cp.scale='default';else cp.scale=scale;
    cp.v5CommonScaleApplied=true;
   }
   else if(cp.v5CommonScaleApplied){cp.scale='default';cp.v5CommonScaleApplied=false;}
   changes++;
  }
 }
 if(!quiet)toast(changes+' new copy settings updated.'+(skipped?' '+skipped+' incompatible setting(s) skipped.':''));
}
applyCommonToSelection=function(){v5ApplyCommonCore(false);renderRows();renderSummary();v5ReviewInitialized=false;};
// Override only the v4 row rendering attributes, retain existing project table design.
var v4ParentRow=parentRow;
parentRow=function(v){var html=v4ParentRow(v),r=state.rows[v.id];
 if(v5On('commonMethodOn')&&r.checked){
  html=html.replace('title="Set number of new copies; 0 means rename only"',
   'readonly onkeydown="return false" onclick="v5LockNotice()" title="Locked to 1. Disable Common Duplication Method to edit."');
 }
 if(v5On('commonMethodOn')&&!v5AllowedSource(v)&&r.checked){html=html.replace('Common method unsupported','Unsupported in Revit');}
 return html;
};
var v4ChildRows=childRows;
childRows=function(v,i,cp){var html=v4ChildRows(v,i,cp);
 if(v5On('commonMethodOn')){
  html=html.replace('title="Duplication method for this copy" onchange=',
   'title="Controlled by Common Duplication Method" disabled onchange=');
  html=html.replace('title="Remove proposed copy"','title="Disable Common Duplication Method to remove copies" disabled');
 }
 return html;
};
// Review Changes is a real tab, not a no-op modal. Checkboxes control which operations Revit receives.
// A single authoritative page switcher. v4's switcher did not know about
// reviewPage; returning from review therefore left two .active-page nodes.
// That pushed/covered Project Views and made editing appear frozen.
tabSelect=function(name){
 if(state.busy)return;
 var map={rename:'renamePage',review:'reviewPage',scope:'scopePage',
          templates:'templatesPage',health:'healthPage',settings:'settingsPage'};
 if(!map[name])return;
 state.tab=name;
 var tabs=document.querySelectorAll('#tabs .tab');
 for(var i=0;i<tabs.length;i++){
  tabs[i].className='tab'+(tabs[i].getAttribute('data-tab')===name?' active':'');
 }
 // Explicitly update ALL pages, including Review Changes, on every transition.
 for(var key in map){
  if(map.hasOwnProperty(key))el(map[key]).className='page'+(key===name?' active-page':'');
 }
 if(name==='rename'){
  // Restore from state (not from the previously hidden DOM): checked rows,
  // live rename inputs, filters, expanded copies and pending settings survive.
  renderFilters();renderRows();renderSummary();
 }else if(name==='review'){
  v5RenderReview();
 }else if(name==='scope'){
  renderScopeList();renderAssignments('scope');
 }else if(name==='templates'){
  renderTemplateList();renderAssignments('template');
 }else if(name==='health' && state.health){
  // Keep existing read-only health results on return.
 }
 updateGlobalApply();
};
var v4GlobalApply=updateGlobalApply;
updateGlobalApply=function(){if(state.tab==='review'){
 el('globalApplyBar').style.display='flex';el('globalApplyTitle').innerText='REVIEW CHANGES';
 el('globalApplyHint').innerText=v5ReviewCountText();el('globalReviewButton').style.display='none';
 el('globalApplyButton').innerText='▶ Apply Checked Changes';return;
 }v4GlobalApply();if(state.tab==='rename'){
 var s=summarize();el('globalApplyHint').innerText=s.selected+' selected · '+s.renames+' renames · '+s.copies+' new views';
 }};
function v5Operations(){var ops=[],job=computeJob();for(var i=0;i<job.items.length;i++){
 var r=job.items[i],src=getView(r.id);if(!src)continue;
 if(r.new_name!==src.name)ops.push({key:'rename:'+r.id,source:src.name,proposed:r.new_name,method:'Rename',settings:'Existing view',kind:'rename',id:r.id});
 for(var j=0;j<r.copies.length;j++){
  var c=r.copies[j],sc=c.scope==='default'?src.scope:c.scope,tpl=c.template==='default'?src.template:c.template;
  ops.push({key:'copy:'+r.id+':'+j,source:src.name,proposed:c.name,method:METHOD_NAMES[c.method],
   settings:'Template: '+entityName(state.templates,tpl)+' · Scope: '+entityName(state.scopes,sc)+' · Scale: '+(c.scale==='default'?'Inherited':formatScale(c.scale)),kind:'copy',id:r.id,idx:j});
 }
 }return ops;}
function v5ReviewCountText(){var all=v5Operations(),n=0;for(var i=0;i<all.length;i++)if(v5ReviewFlags[all[i].key]!==false)n++;return n+' of '+all.length+' operations selected';}
function v5RenderReview(){var ops=v5Operations(),html='<div class="review-row heading"><span>APPLY</span><span>ORIGINAL VIEW</span><span>PROPOSED VIEW NAME</span><span>OPERATION</span><span>SETTINGS</span></div>';
 if(!v5ReviewInitialized){v5ReviewFlags={};for(var i=0;i<ops.length;i++)v5ReviewFlags[ops[i].key]=true;v5ReviewInitialized=true;}
 for(var j=0;j<ops.length;j++){var op=ops[j],checked=v5ReviewFlags[op.key]!==false;
  html+='<div class="review-row"><input type="checkbox" '+(checked?'checked':'')+' onclick="v5ReviewToggle(\''+h(op.key)+'\',this.checked)">'+
  '<strong>'+h(op.source)+'</strong><span>'+h(op.proposed)+'</span><span>'+h(op.method)+'</span><span class="muted">'+h(op.settings)+'</span></div>';
 }
 el('reviewRows').innerHTML=ops.length?html:'<p class="muted" style="padding:20px">No renames or new views are currently proposed. Configure checked views first.</p>';
 el('reviewCount').innerText=v5ReviewCountText();
 var issues=getConflicts(v5ReviewedJob()),warnings='';for(var x=0;x<issues.length;x++)warnings+='<div>⚠ '+h(issues[x])+'</div>';
 el('reviewWarnings').innerHTML=warnings;updateGlobalApply();
}
function v5ReviewToggle(key,checked){v5ReviewFlags[key]=checked;v5RenderReview();}
function v5ReviewCheckAll(checked){var ops=v5Operations();for(var i=0;i<ops.length;i++)v5ReviewFlags[ops[i].key]=checked;v5RenderReview();}
function v5ReviewedJob(){var job=computeJob(),out=[];for(var i=0;i<job.items.length;i++){
 var row=job.items[i],src=getView(row.id),copies=[];
 for(var j=0;j<row.copies.length;j++)if(v5ReviewFlags['copy:'+row.id+':'+j]!==false)copies.push(row.copies[j]);
 var rename=src&&row.new_name!==src.name&&v5ReviewFlags['rename:'+row.id]!==false;
 if(rename||copies.length){out.push({id:row.id,new_name:rename?row.new_name:src.name,scope:'default',copies:copies});}
 }return{items:out};}
previewRename=function(){tabSelect('review');};
function v5SubmitReview(){if(state.busy)return;var job=v5ReviewedJob();
 if(!job.items.length){toast('Select one or more operations to apply.');return;}
 var issues=getConflicts(job);if(issues.length){v5RenderReview();toast('Resolve the review conflicts before applying.');return;}
 var nr=0,nc=0;for(var i=0;i<job.items.length;i++){var row=job.items[i],v=getView(row.id);if(v&&row.new_name!==v.name)nr++;nc+=row.copies.length;}
 if(!confirm('Apply '+nr+' rename(s) and create '+nc+' new view(s)?\n\nOnly checked Review Changes operations will be committed.'))return;
 state.busy=true;state.v5RetainFilters=true;
 if(nc>0&&el('humorToggle').checked){showProcessing(true);setTimeout(function(){host('apply',job);},70);}else host('apply',job);
}
var v4ApplyWorkspace=applyCurrentWorkspace;
applyCurrentWorkspace=function(){if(state.tab==='review')return v5SubmitReview();
 if(state.tab==='rename'){tabSelect('review');toast('Review the selected operations, then click Apply Checked Changes.');return;}
 return v4ApplyWorkspace();};
submitChanges=function(){tabSelect('review');};
// Preserve view-type filters and optional search after Revit refreshes metadata.
var v4HostData=setHostData;
setHostData=function(raw){var wasLoaded=state.hostReady,filter=clone(state.filter),q=el('searchInput').value,project=state.project,tab=state.tab;
 v4HostData(raw);
 if(wasLoaded&&project===state.project){state.filter=filter;el('searchInput').value=q;
  renderFilters();renderRows();renderSummary();}
 if(wasLoaded&&tab==='scope'||wasLoaded&&tab==='templates')tabSelect(tab);
 if(wasLoaded&&state.v5RetainFilters){state.v5RetainFilters=false;v5ReviewInitialized=false;tabSelect('rename');}
 v5WasCommonOn=false;v5ToggleCommon();syncBimHumor();
};
var v4ShowApplyResults=showApplyResults;
showApplyResults=function(raw){v4ShowApplyResults(raw);state.v5RetainFilters=true;};
var v4CapturePreset=capturePreset;
capturePreset=function(){var obj=v4CapturePreset(),fields=['Scope','Template','Method','Scale'];for(var i=0;i<fields.length;i++)obj['common'+fields[i]+'On']=v5On('common'+fields[i]+'On');return obj;};
var v4LoadPreset=loadSelectedPreset;
loadSelectedPreset=function(){var key=el('presetSelect').value,p=state.presets[key];v4LoadPreset();if(!p)return;
 var fields=['Scope','Template','Method','Scale'];for(var i=0;i<fields.length;i++)if(p['common'+fields[i]+'On']!==undefined)el('common'+fields[i]+'On').checked=!!p['common'+fields[i]+'On'];v5ToggleCommon();};
// Template and Scope Box manager: user-triggered operations (no silent project edits).
function v5ManageEntity(mode,operation){var a=assignmentUI[mode],item=getAssignmentSource(mode,a.selected);
 if(!item){toast('Select a '+(mode==='scope'?'scope box':'view template')+' first.');return;}
 var payload={mode:mode,operation:operation,id:item.id},name;
 if(operation==='rename'||operation==='duplicate'){
  name=prompt(operation==='rename'?'Rename this item to:':'Name for the new duplicate:',operation==='rename'?item.name:item.name+' - Copy');
  if(name===null)return;name=name.replace(/^\s+|\s+$/g,'');if(!name){toast('A name is required.');return;}payload.name=name;
 }else if(operation==='edit'){
  if(mode==='template'){
   var choice=prompt('Edit View Template: set its drawing scale ratio (for example 48 for 1/4" = 1\'-0", or 100 for 1:100).\nTo edit other template settings, use Revit native View Templates settings.',String(item.scale||100));
   if(choice===null)return;var ratio=parseInt(choice,10);if(!ratio||ratio<1||ratio>100000){toast('Enter a valid positive drawing ratio.');return;}payload.scale=ratio;
  }else{
   var offset=prompt('Edit Scope Box position. Enter X,Y,Z offsets in feet (example: 1,0,0 moves the scope box 1 ft in X). For resizing, edit the scope box in Revit.', '0,0,0');
   if(offset===null)return;var parts=offset.split(',');if(parts.length!==3||isNaN(Number(parts[0]))||isNaN(Number(parts[1]))||isNaN(Number(parts[2]))){toast('Enter three numeric offsets X,Y,Z.');return;}
   payload.offset=[Number(parts[0]),Number(parts[1]),Number(parts[2])];
  }
 }
 if(!confirm('Apply '+operation+' to '+item.name+'?\nThis modifies the current Revit project.'))return;
 state.busy=true;host('manage_entity',payload);
}
function v5ManageResults(raw){var res=typeof raw==='string'?JSON.parse(raw):raw;state.busy=false;
 showModal('ViewPilot — Management Complete','<p class="status-ok">'+h(res.message)+'</p>');
}

// New copies never silently inherit a disabled Common Setting.
var v4NewCopy=newCopy;
newCopy=function(view,index,method){var cp=v4NewCopy(view,index,method);
 if(!v5On('commonScopeOn'))cp.scope='default';
 if(!v5On('commonTemplateOn'))cp.template='default';
 if(!v5On('commonScaleOn'))cp.scale='default';
 return cp;
};
// Parent Scope column controls COPY settings only; the original is never edited.
changeParentScope=function(id,value){var r=state.rows[id];r.scope=value;
 for(var i=0;i<r.copies.length;i++){r.copies[i].scope=value;r.copies[i].v5CommonScopeApplied=false;}
 renderRows();renderSummary();v5ReviewInitialized=false;};

function updateCopiesResetControls(){var locked=v5On('commonMethodOn'),message='Turn off Common Duplication Method to reset or configure individual copy counts.';
 el('copiesResetButton').disabled=locked;el('copiesResetScope').disabled=locked;
 el('copiesResetButton').title=locked?message:'Remove pending copies in the chosen scope; keep source views and renames.';
 el('copiesResetHint').style.display=locked?'block':'none';
}
function resetCopies(){
 if(state.busy)return;
 if(v5On('commonMethodOn')){toast('Turn off Common Duplication Method to reset or configure individual copy counts.');return;}
 var ids=el('copiesResetScope').value==='visible'?(function(){var views=visibleViews(),out=[];
  for(var i=0;i<views.length;i++)out.push(views[i].id);return out;})():sortedIds();
 var removed=0;
 for(var i=0;i<ids.length;i++){var id=ids[i],r=state.rows[id];if(!r)continue;
  removed+=r.copies.length;r.count=0;r.method='none';r.copies=[];state.expanded[id]=false;
  // Keep rename selections and all unrelated review-operation selections.
  var prefix='copy:'+id+':';for(var key in v5ReviewFlags)if(v5ReviewFlags.hasOwnProperty(key)&&key.indexOf(prefix)===0)delete v5ReviewFlags[key];
 }
 renderRows();renderSummary();v5RenderReview();
 toast(removed+' pending cop'+(removed===1?'y':'ies')+' reset to 0. Renames are unchanged.');
}

// One shuffled deck and one timer for the entire window, independent of tabs.
var bimHumorTimer=null,bimJokeDeck=[],bimCurrentJoke='',bimHumorDisposed=false;
function nextBimJoke(){
 if(bimHumorDisposed||state.busy||state.settings.humor===false)return;
 if(!bimJokeDeck.length){
  for(var i=0;i<humorLines.length;i++)bimJokeDeck.push(humorLines[i]);
  for(var j=bimJokeDeck.length-1;j>0;j--){var k=Math.floor(Math.random()*(j+1)),temp=bimJokeDeck[j];bimJokeDeck[j]=bimJokeDeck[k];bimJokeDeck[k]=temp;}
  // Do not repeat the last joke across deck boundaries either.
  var last=bimJokeDeck.length-1;
  if(last>0&&bimJokeDeck[last]===bimCurrentJoke){var swap=bimJokeDeck[0];bimJokeDeck[0]=bimJokeDeck[last];bimJokeDeck[last]=swap;}
 }
 bimCurrentJoke=bimJokeDeck.pop();el('footerJoke').innerText=bimCurrentJoke;
}
function syncBimHumor(){
 var enabled=state.settings.humor!==false&&!bimHumorDisposed;
 el('humorToggle').checked=enabled;el('footerHumorToggle').checked=enabled;
 el('footerHumorStatus').innerText=enabled?'On':'Off';
 el('footerJoke').style.display=enabled?'':'none';el('nextJokeButton').disabled=!enabled;
 el('footerJoke').parentNode.className='footer-group bim-humor'+(enabled?'':' humor-off');
 if(!enabled){if(bimHumorTimer!==null){clearInterval(bimHumorTimer);bimHumorTimer=null;}return;}
 if(!bimCurrentJoke)nextBimJoke();
 if(bimHumorTimer===null)bimHumorTimer=setInterval(nextBimJoke,60000);
}
function disposeViewPilot(){
 bimHumorDisposed=true;
 if(bimHumorTimer!==null){clearInterval(bimHumorTimer);bimHumorTimer=null;}
 if(toastTimer!==null){clearTimeout(toastTimer);toastTimer=null;}
 bimJokeDeck=[];
}
window.addEventListener('pagehide',disposeViewPilot,false);
window.addEventListener('unload',disposeViewPilot,false);
