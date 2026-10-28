const STYLE = `
#hx-fab{position:fixed;right:20px;bottom:calc(20px + env(safe-area-inset-bottom));z-index:99999;display:inline-flex;align-items:center;gap:8px;border:0;border-radius:999px;padding:12px 18px;background:linear-gradient(135deg,#1f6feb,#7b2ff7);color:#fff;font:600 13px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.5);cursor:pointer}
#hx-fab:hover{filter:brightness(1.08)}
#hx-fab:focus-visible{outline:2px solid #93c5fd;outline-offset:2px}
#hx-fab-badge{display:none;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:rgba(255,255,255,.24);font-size:11px;line-height:1}
.hx-backdrop{position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,.62);backdrop-filter:blur(2px)}
.hx-backdrop[hidden]{display:none!important}
.hx-shell{position:fixed;z-index:99999;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;width:min(1040px,calc(100vw - 32px));height:86vh;height:86dvh;max-height:920px;background:#111113;border:1px solid #2c2c30;border-radius:14px;box-shadow:0 24px 80px rgba(0,0,0,.7);overflow:hidden;color:#eee;font:13px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-shell[hidden]{display:none!important}
.hx-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px 10px;border-bottom:1px solid #232327}
.hx-head-title{font:650 16px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#fff;margin:0}
.hx-head-sub{display:block;color:#a1a1aa;font:12px system-ui;margin-top:3px}
.hx-icon-btn{appearance:none;border:1px solid #333338;background:#1a1a1d;color:#c9ccd1;border-radius:9px;width:38px;height:38px;font:22px/1 system-ui;cursor:pointer;display:grid;place-items:center}
.hx-icon-btn:hover{background:#252529;color:#fff}
.hx-tabs{display:flex;gap:4px;padding:8px 14px 0;border-bottom:1px solid #232327;overflow-x:auto;scrollbar-width:none;flex:0 0 auto}
.hx-tabs::-webkit-scrollbar{display:none}
.hx-tab{appearance:none;border:0;border-bottom:2px solid transparent;background:transparent;color:#9aa0a6;padding:10px 14px;border-radius:8px 8px 0 0;font:600 13px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:7px}
.hx-tab:hover{color:#e5e7eb;background:#17171a}
.hx-tab[aria-selected="true"]{color:#fff;background:#19191c;border-bottom-color:#60a5fa}
.hx-tab:focus-visible{outline:2px solid #3b82f6;outline-offset:-2px}
.hx-tab-count{display:flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#2a2a30;color:#c9ccd1;font-size:10px}
.hx-tab-count[hidden]{display:none!important}
.hx-body{flex:1 1 auto;overflow:auto;padding:16px 18px 26px;overscroll-behavior:contain;scrollbar-width:thin}
.hx-pane[hidden]{display:none!important}
.hx-muted{color:#9aa0a6}
.hx-warn{color:#f59e0b;white-space:pre-wrap}
.hx-error{color:#f87171;white-space:pre-wrap;margin-top:4px}
.hx-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.hx-input,.hx-select{background:#1a1a1d;border:1px solid #333338;color:#eee;border-radius:8px;padding:8px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:36px;outline:none;min-width:0}
.hx-input{flex:1 1 220px}
.hx-select{flex:0 1 190px}
.hx-input:focus,.hx-select:focus{border-color:#3b82f6;box-shadow:0 0 0 2px rgba(59,130,246,.18)}
.hx-btn{appearance:none;cursor:pointer;border:1px solid #3a3a3f;background:#1d1d21;color:#eee;border-radius:8px;padding:8px 11px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:36px;line-height:1.2}
.hx-btn:hover{background:#252529}
.hx-btn:disabled{opacity:.5;cursor:default}
.hx-btn:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-btn-primary{background:#1f6feb;border-color:#1f6feb;color:#fff}
.hx-btn-primary:hover{background:#2b7bf5}
.hx-btn-ok{background:#1f7a3d;border-color:#1f7a3d;color:#fff}
.hx-btn-ok:hover{background:#248a45}
.hx-quota{border:1px solid #26262b;background:#151518;border-radius:10px;padding:10px 12px;margin-bottom:10px}
.hx-quota-line{font-size:12px;color:#c9ccd1;white-space:pre-wrap}
.hx-bar{height:6px;border-radius:999px;background:#26262b;overflow:hidden;margin:7px 0 0}
.hx-bar>span{display:block;height:100%;background:#60a5fa;width:0;transition:width .3s ease}
.hx-summary{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px}
.hx-chip{appearance:none;cursor:pointer;border:1px solid #2f2f35;background:#17171a;color:#c9ccd1;border-radius:999px;padding:6px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:inline-flex;align-items:center;gap:6px}
.hx-chip:hover{background:#202024}
.hx-chip[aria-pressed="true"]{border-color:#60a5fa;background:rgba(96,165,250,.12);color:#fff}
.hx-chip b{font-weight:700}
.hx-dot{width:7px;height:7px;border-radius:999px;display:inline-block}
.hx-order{border:1px solid #26262b;border-radius:10px;background:#151518;padding:11px 12px;margin-bottom:8px}
.hx-order-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.hx-order-title{min-width:0;color:#f1f2f4;font:600 13px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-kind{display:inline-block;color:#a1a1aa;font:600 11px system-ui;text-transform:uppercase;letter-spacing:.04em;margin-right:6px}
.hx-status{flex:0 0 auto;border-radius:999px;padding:3px 8px;font:600 10px system-ui;border:1px solid transparent;white-space:nowrap}
.hx-status-downloaded{color:#4ade80;background:rgba(74,222,128,.11);border-color:rgba(74,222,128,.28)}
.hx-status-partial{color:#2dd4bf;background:rgba(45,212,191,.11);border-color:rgba(45,212,191,.28)}
.hx-status-downloading{color:#60a5fa;background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.3)}
.hx-status-queued{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-status-searching{color:#c084fc;background:rgba(192,132,252,.12);border-color:rgba(192,132,252,.3)}
.hx-status-error{color:#f87171;background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.3)}
.hx-status-missing{color:#a1a1aa;background:rgba(161,161,170,.1);border-color:rgba(161,161,170,.25)}
.hx-order-meta{color:#a1a1aa;font-size:12px;margin-top:3px;overflow-wrap:anywhere}
.hx-order-event{color:#a1a1aa;font-size:12px;margin-top:3px;overflow-wrap:anywhere}
.hx-order-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.hx-order-result{color:#a1a1aa;font-size:12px;margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}
#hx-storage{margin:1rem 1.25rem .5rem;padding:12px 14px;border:1px solid #26262b;border-radius:12px;background:#151518;color:#e5e7eb}
#hx-storage[hidden]{display:none!important}
body.hx-tab-active #hx-storage{display:none!important}
.hx-storage-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.hx-storage-title{font:600 13px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#f1f2f4}
.hx-storage-meta{display:flex;align-items:center;gap:10px;min-width:0}
.hx-storage-updated{font:12px system-ui;color:#9aa0a6;white-space:nowrap}
.hx-storage-refresh{appearance:none;border:0;background:transparent;color:#60a5fa;cursor:pointer;font:12px system-ui;padding:0}
.hx-storage-refresh:hover{color:#93c5fd}
.hx-storage-refresh:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-storage-row{padding:8px 0;border-top:1px solid #202024}
.hx-storage-row:first-of-type{border-top:0;padding-top:0}
.hx-storage-line{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.hx-storage-label{min-width:0;font:600 12px system-ui;color:#e5e7eb;overflow-wrap:anywhere}
.hx-storage-kind{display:inline-block;margin-left:6px;color:#a1a1aa;font:600 11px system-ui;text-transform:uppercase;letter-spacing:.04em}
.hx-storage-value{font:12px system-ui;color:#c9ccd1;white-space:nowrap}
.hx-storage-bar{height:7px;border-radius:999px;background:#26262b;overflow:hidden;margin-top:6px}
.hx-storage-bar>span{display:block;height:100%;width:0;background:#4ade80;transition:width .3s ease}
.hx-storage-sub{font:12px system-ui;color:#9aa0a6;margin-top:4px;overflow-wrap:anywhere}
.hx-storage-empty{font:12px system-ui;color:#8f949b;padding:4px 0}
@media(min-width:640px){#hx-storage{margin:1rem 2.25rem .5rem}}
.hx-viewbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.hx-seg{display:inline-flex;gap:3px;padding:3px;border:1px solid #333338;border-radius:999px;background:#17171a}
.hx-seg .hx-btn{border:0;border-radius:999px;background:transparent;color:#9aa0a6;min-height:30px;padding:6px 14px}
.hx-seg .hx-btn[aria-pressed="true"]{background:#1f6feb;color:#fff}
.hx-summary[hidden],.hx-episode-section[hidden],.hx-history-section[hidden]{display:none!important}
.hx-status-request_pending{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-status-request_approved{color:#60a5fa;background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.3)}
.hx-status-request_declined,.hx-status-request_failed{color:#f87171;background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.3)}
.hx-status-request_completed{color:#4ade80;background:rgba(74,222,128,.11);border-color:rgba(74,222,128,.28)}
.hx-status-requested{color:#fbbf24;background:rgba(251,191,36,.11);border-color:rgba(251,191,36,.28)}
.hx-episode-rows{margin-top:8px}
.hx-episode-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid #202024}
.hx-episode-main{min-width:0;flex:1 1 auto}
.hx-episode-title{color:#e5e7eb;font:600 12px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-episode-sub{color:#9aa0a6;font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.hx-episode-side{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.hx-group{margin:16px 0 4px}
.hx-group:first-child{margin-top:4px}
.hx-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 0 6px;border-bottom:1px solid #2a2a30}
.hx-group-title{min-width:0;color:#e5e7eb;font:600 13px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-ep{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #202024}
.hx-ep-label{min-width:0;color:#d4d4d8;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-ep-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist{display:grid;grid-template-columns:92px minmax(0,1fr) auto;gap:4px 12px;align-items:start;border:1px solid #26262b;border-radius:8px;background:#151518;padding:8px 10px;margin-bottom:6px}
.hx-hist-date{font:600 12px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#c9ccd1}
.hx-hist-date-label{display:block;color:#9aa0a6;font:11px system-ui;text-transform:uppercase;letter-spacing:.04em}
.hx-hist-time{display:block;color:#9aa0a6;font:11px system-ui}
.hx-hist-main{min-width:0}
.hx-hist-title{color:#f1f2f4;font:600 12.5px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-hist-meta{color:#a1a1aa;font:12px/1.4 system-ui;margin-top:2px;overflow-wrap:anywhere}
.hx-hist-event{color:#a1a1aa;font:12px/1.4 system-ui;margin-top:2px;overflow-wrap:anywhere}
.hx-hist-side{display:flex;flex-direction:column;align-items:flex-end;gap:5px}
.hx-hist-badges{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist-badge{border-radius:999px;padding:2px 7px;font:600 10px system-ui;border:1px solid transparent;white-space:nowrap}
.hx-hist-badge-active{color:#60a5fa;background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.28)}
.hx-hist-badge-archived{color:#c084fc;background:rgba(192,132,252,.1);border-color:rgba(192,132,252,.28)}
.hx-hist-actions{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
.hx-hist-actions .hx-btn{min-height:32px;padding:5px 9px;font-size:12px}
.hx-empty{padding:28px 10px;text-align:center;color:#a1a1aa;font-size:12px}
.hx-ext-link{display:inline-flex;align-items:center;color:#60a5fa;text-decoration:none;font:12px system-ui;padding:4px 6px;border-radius:6px}
.hx-ext-link:hover{color:#93c5fd;text-decoration:underline}
.hx-ext-link:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-sep{height:1px;background:#232327;margin:12px 0}
@media(max-width:700px){
  #hx-fab{right:14px;bottom:calc(14px + env(safe-area-inset-bottom));padding:11px 16px}
  .hx-shell{left:0;top:0;transform:none;width:100vw;height:100vh;height:100dvh;max-height:none;border-radius:0;border:0}
  .hx-head{padding:12px 14px 8px}
  .hx-tabs{padding:6px 10px 0}
  .hx-tab{flex:1;justify-content:center;padding:11px 8px}
  .hx-body{padding:12px 14px 30px}
  .hx-input{flex:1 1 100%}
  .hx-select{flex:1 1 100%}
  .hx-toolbar .hx-btn{flex:1 1 auto}
  .hx-order{padding:10px}
  .hx-order-top{flex-direction:column;gap:5px}
  .hx-status{align-self:flex-start}
  .hx-ep{align-items:flex-start}
  .hx-episode-row{flex-direction:column;gap:5px}
  .hx-episode-side{justify-content:flex-start}
  .hx-seg{width:100%}
  .hx-seg .hx-btn{flex:1 1 auto}
  #hx-storage{margin:1rem 1.25rem .5rem;padding:10px 12px}
  .hx-storage-line{flex-direction:column;gap:2px;align-items:flex-start}
  .hx-storage-value{white-space:normal}
  .hx-storage-updated{display:none}
  .hx-toolbar .hx-search{order:-2;flex:1 1 55%}
  .hx-toolbar .hx-refresh{order:-1;flex:0 0 auto}
  .hx-summary{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
  .hx-summary::-webkit-scrollbar{display:none}
  .hx-summary .hx-chip{flex:0 0 auto}
  .hx-ep-remove{min-height:40px;padding:8px 10px;font-size:12px}
  .hx-episode-note{display:none}
  .hx-hist{grid-template-columns:1fr;gap:5px;padding:8px 10px}
  .hx-hist-date{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}
  .hx-hist-date-label,.hx-hist-time{display:inline}
  .hx-hist-side{flex-direction:row;align-items:center;justify-content:space-between}
  .hx-hist-badges{justify-content:flex-start}
  .hx-storage-refresh{padding:6px 8px;border-radius:4px}
  body.hx-tab-active #information-widgets{margin:8px 8px 0;padding:6px 8px}
  body.hx-tab-active #information-widgets .widget-container:has(.information-widget-resource){display:none}
  body.hx-tab-active #information-widgets input[type="text"]{padding:8px 10px;font-size:13px;min-height:36px}
  body.hx-tab-active #information-widgets .information-widget-datetime .text-xl{font-size:16px}
  body.hx-tab-active .hx-help{padding:6px 10px;font-size:12px}
  body.hx-tab-active .hx-help summary{padding:1px 0}
}
body.hx-has-nav #inner_wrapper{padding-top:50px!important}
#hx-nav,#hx-nav *,#hx-view,#hx-view *{box-sizing:border-box}
#hx-nav{position:fixed;top:0;left:0;right:0;z-index:35;height:50px;background:rgba(15,15,17,.96);backdrop-filter:blur(8px);border-bottom:1px solid #26262b;box-shadow:0 2px 14px rgba(0,0,0,.28)}
#hx-nav-inner{height:100%;max-width:1536px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:4px;overflow-x:auto;scrollbar-width:none}
#hx-nav-inner::-webkit-scrollbar{display:none}
.hx-nav-tab{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;text-decoration:none;color:#9aa0a6;background:transparent;border:0;border-radius:8px;padding:8px 13px;font:600 13px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;cursor:pointer;transition:background .15s,color .15s}
.hx-nav-tab:hover{color:#e5e7eb;background:#1b1b1f}
.hx-nav-tab[aria-selected="true"]{color:#fff;background:rgba(96,165,250,.14);box-shadow:inset 0 -2px 0 #60a5fa}
.hx-nav-tab:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-nav-count{display:flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#2a2a30;color:#c9ccd1;font-size:10px}
.hx-nav-count[hidden]{display:none!important}
#hx-view{width:100%;padding:14px 20px 40px}
#hx-view[hidden]{display:none!important}
.hx-pane[hidden]{display:none!important}
body.hx-tab-active .services-group,
body.hx-tab-active #bookmarks,
body.hx-tab-active #footer{display:none!important}
@media(max-width:700px){
  body.hx-has-nav #inner_wrapper{padding-top:50px!important}
  #hx-nav-inner{padding:0 8px;gap:2px}
  .hx-nav-tab{flex:1;justify-content:center;padding:9px 6px;font-size:12.5px}
  #hx-view{padding:10px 12px 30px}
  .hx-addbody{position:sticky;top:50px;z-index:20;background:#111113}
}
.hx-addbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.hx-addbar[hidden]{display:none!important}
.hx-addbody{border:1px solid #26262b;border-radius:10px;background:#131316;padding:10px 12px;margin-bottom:10px}
.hx-addbody[hidden]{display:none!important}
.hx-addbody .hx-input{flex:1 1 100%;margin-bottom:8px}
.hx-lookup{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #202024}
.hx-lookup:last-child{border-bottom:0;padding-bottom:0}
.hx-lookup-poster{width:46px;height:69px;object-fit:cover;border-radius:6px;background:#1c1c20;flex:0 0 auto}
.hx-lookup-main{min-width:0;flex:1 1 auto}
.hx-lookup-title{color:#f1f2f4;font:600 13px/1.3 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.hx-lookup-meta{color:#a1a1aa;font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.hx-lookup-actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}
.hx-lookup-form{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.hx-lookup-form .hx-select{flex:1 1 150px}
.hx-field{display:flex;flex-direction:column;gap:4px;flex:1 1 150px;min-width:0;font:12px system-ui;color:#9aa0a6}
.hx-field .hx-select{flex:1 1 auto}
.hx-season{border:1px solid #26262b;border-radius:10px;margin-bottom:8px;overflow:hidden}
.hx-season[hidden],.hx-ep-row[hidden]{display:none!important}
.hx-season-head{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#17171a;border-bottom:1px solid #26262b;font:600 12px system-ui;color:#e5e7eb;cursor:pointer;list-style:none}
.hx-season-head::-webkit-details-marker{display:none}
.hx-season-head::before{content:'▸';color:#9aa0a6;font-size:11px;flex:0 0 auto;transition:transform .15s}
details[open]>.hx-season-head::before{content:'▾'}
.hx-season-head input,.hx-ep-row input{accent-color:#3b82f6;width:15px;height:15px;flex:0 0 auto;margin:0}
.hx-ep-row{display:flex;align-items:flex-start;gap:8px;padding:7px 10px;border-bottom:1px solid #202024;font:12px system-ui;color:#d4d4d8;cursor:pointer}
.hx-ep-row:last-child{border-bottom:0}
.hx-ep-row:hover{background:#18181b}
.hx-ep-num{color:#9aa0a6;font-variant-numeric:tabular-nums;flex:0 0 auto;min-width:62px}
.hx-ep-name{min-width:0;flex:1 1 auto;overflow-wrap:anywhere}
.hx-ep-tag{flex:0 0 auto;border-radius:999px;padding:2px 7px;font:600 10px system-ui;color:#4ade80;background:rgba(74,222,128,.11);border:1px solid rgba(74,222,128,.28)}
.hx-ep-tag-request{color:#c084fc;background:rgba(192,132,252,.12);border-color:rgba(192,132,252,.3)}
.hx-ep-foot{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 0 0;position:sticky;bottom:0;background:#111113;border-top:1px solid #232327;margin-top:8px}
.hx-check{display:inline-flex;align-items:center;gap:6px;color:#c9ccd1;font:12px system-ui;cursor:pointer}
.hx-check input{accent-color:#3b82f6;width:15px;height:15px;margin:0}
.hx-filters-btn[hidden]{display:none!important}
.hx-filters-btn[data-count]:not([data-count="0"]){border-color:#60a5fa;background:rgba(96,165,250,.12);color:#fff}
.hx-shell-filters{width:min(620px,calc(100vw - 32px));height:auto;max-height:86vh;max-height:86dvh;min-height:0}
.hx-filter-group{margin-bottom:14px}
.hx-filter-label{display:block;color:#c9ccd1;font:600 12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin-bottom:6px}
.hx-filter-chips{display:flex;flex-wrap:wrap;gap:6px}
.hx-filter-status-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.hx-filter-status-head .hx-filter-label{margin-bottom:0}
.hx-filter-status-actions{display:flex;gap:6px}
.hx-filter-status-actions .hx-btn{min-height:28px;padding:4px 8px;font-size:11px}
.hx-filter-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 14px;max-height:260px;overflow:auto;padding-right:4px}
.hx-filter-actions{display:flex;align-items:center;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #232327}
.hx-filter-actions .hx-btn:first-child{margin-right:auto}
.hx-pager{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:4px;margin:14px 0 4px}
.hx-pager[hidden]{display:none!important}
.hx-page{appearance:none;cursor:pointer;border:1px solid #2f2f35;background:#17171a;color:#c9ccd1;border-radius:8px;min-width:34px;min-height:34px;padding:6px 10px;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-page:hover{background:#202024}
.hx-page[aria-current="page"]{background:#1f6feb;border-color:#1f6feb;color:#fff}
.hx-page:disabled{opacity:.45;cursor:default}
.hx-page:focus-visible{outline:2px solid #3b82f6;outline-offset:1px}
.hx-page-info{color:#9aa0a6;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0 6px}
@media(max-width:700px){
  .hx-shell-filters{left:0;top:0;transform:none;width:100vw;height:100vh;height:100dvh;max-height:none;border-radius:0;border:0}
  .hx-filter-grid{grid-template-columns:1fr;max-height:none}
  .hx-filter-actions{position:sticky;bottom:0;background:#111113}
  .hx-page-info{flex:1 1 100%;text-align:center;order:3;margin:4px 0 0}
}
.hx-help{border:1px solid #26262b;background:#151518;border-radius:10px;padding:9px 12px;margin-bottom:10px;color:#c9ccd1;font:12px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.hx-help summary{cursor:pointer;color:#e5e7eb;font-weight:600;outline:none}
.hx-help summary:focus-visible{outline:2px solid #3b82f6;outline-offset:2px;border-radius:4px}
.hx-help ul{margin:8px 0 0 18px;padding:0}
.hx-help li{margin:3px 0}
.hx-view-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hx-btn-link{display:inline-flex;align-items:center;background:transparent;border:0;color:#60a5fa;padding:0;min-height:auto;font:12px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-decoration:none}
.hx-btn-link::before{content:'• ';color:#8f949b}
.hx-btn-link:hover{color:#93c5fd;text-decoration:underline}
.hx-btn-link[hidden]{display:none!important}
`;

export function injectStyles() {
  if (document.getElementById('hx-style')) return;
  const style = document.createElement('style');
  style.id = 'hx-style';
  style.textContent = STYLE;
  document.head.appendChild(style);
}
