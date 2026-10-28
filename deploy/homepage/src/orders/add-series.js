import { countLabel, h, btn, toast } from '../shared.js';
import { profileLabel, seriesTypeLabel, ordersApi } from './common.js';

export function createAddSeries(ctx) {
  const { helpers } = ctx;
  let optionsData = null;
  let optionsPromise = null;
  let lookupTimer = 0;

  const addInput = h('input', 'hx-input');
  addInput.type = 'search';
  addInput.placeholder = 'Buscar série/anime (mín. 3 letras)...';
  addInput.setAttribute('aria-label', 'Buscar série ou anime no Sonarr');
  const addResults = h('div', '', '');
  const addBody = h('div', 'hx-addbody', '');
  addBody.hidden = true;
  addBody.append(addInput, addResults);
  const addToggle = btn('Adicionar série/anime', 'hx-btn-primary', () => open());
  const addbar = h('div', 'hx-addbar', '');
  addbar.appendChild(addToggle);

  function show() {
    addBody.hidden = false;
    addInput.focus();
    loadOptions().catch((e) => {
      addResults.innerHTML = '';
      addResults.appendChild(h('div', 'hx-error', 'Erro: ' + e.message));
    });
  }

  function open() {
    addBody.hidden = !addBody.hidden;
    if (!addBody.hidden) show();
  }

  function setActive(active) {
    addbar.hidden = !active;
    addBody.hidden = true;
  }

  function close() {
    addBody.hidden = true;
  }

  function loadOptions() {
    if (optionsData) return Promise.resolve(optionsData);
    if (!optionsPromise) {
      optionsPromise = ordersApi('/sonarr/options').then((data) => {
        optionsData = data;
        return data;
      }).catch((e) => {
        optionsPromise = null;
        throw e;
      });
    }
    return optionsPromise;
  }

  async function runLookup() {
    const term = addInput.value.trim();
    if (term.length < 3) {
      addResults.innerHTML = '';
      return;
    }
    addResults.innerHTML = '';
    addResults.appendChild(h('div', 'hx-muted', 'Buscando no Sonarr...'));
    try {
      const [data] = await Promise.all([
        ordersApi('/sonarr/lookup?term=' + encodeURIComponent(term)),
        loadOptions(),
      ]);
      renderLookup(data.results || []);
    } catch (e) {
      addResults.innerHTML = '';
      addResults.appendChild(h('div', 'hx-error', 'Erro: ' + e.message));
    }
  }

  addInput.addEventListener('input', () => {
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(runLookup, 600);
  });

  function renderLookup(rows) {
    addResults.innerHTML = '';
    if (!rows.length) {
      addResults.appendChild(h('div', 'hx-muted', 'Nada encontrado.'));
      return;
    }
    for (const row of rows) addResults.appendChild(renderLookupRow(row));
  }

  function renderLookupRow(row) {
    const box = h('div', 'hx-lookup', '');
    if (row.poster) {
      const poster = h('img', 'hx-lookup-poster');
      poster.src = row.poster;
      poster.alt = '';
      poster.loading = 'lazy';
      box.appendChild(poster);
    } else {
      box.appendChild(h('div', 'hx-lookup-poster', ''));
    }
    const main = h('div', 'hx-lookup-main', '');
    main.appendChild(h('div', 'hx-lookup-title', row.title + (row.year ? ' (' + row.year + ')' : '')));
    const bits = [seriesTypeLabel(row.seriesType)];
    if (row.network) bits.push(row.network);
    if (row.seasons) bits.push(countLabel(row.seasons, 'temporada', 'temporadas'));
    if (row.status) bits.push(row.status);
    main.appendChild(h('div', 'hx-lookup-meta', bits.join(' • ')));
    if (row.overview) {
      const overview = h('div', 'hx-lookup-meta', row.overview);
      overview.style.display = '-webkit-box';
      overview.style.webkitLineClamp = '2';
      overview.style.webkitBoxOrient = 'vertical';
      overview.style.overflow = 'hidden';
      main.appendChild(overview);
    }

    const actions = h('div', 'hx-lookup-actions', '');
    let form = null;
    if (row.existing) {
      const existing = row.existing;
      actions.appendChild(h('span', 'hx-muted', 'No Sonarr • perfil ' + (profileLabel(existing.profileName) || existing.profileId)));
      actions.appendChild(btn('Episódios', 'hx-btn-primary', () => helpers.openEpisodes(existing.id, false)));
    } else {
      actions.appendChild(btn('Adicionar', 'hx-btn-ok', () => {
        form.hidden = !form.hidden;
        if (!form.hidden) form.scrollIntoView({ block: 'nearest' });
      }));
    }
    main.appendChild(actions);

    if (!row.existing) {
      form = h('div', 'hx-lookup-form', '');
      form.hidden = true;
      const profileSel = h('select', 'hx-select');
      profileSel.setAttribute('aria-label', 'Perfil');
      const rootSel = h('select', 'hx-select');
      rootSel.setAttribute('aria-label', 'Pasta raiz');
      const typeSel = h('select', 'hx-select');
      typeSel.setAttribute('aria-label', 'Tipo de série');
      for (const item of [['standard', 'Padrão'], ['anime', 'Anime'], ['daily', 'Diário']]) {
        const opt = h('option', '', item[1]);
        opt.value = item[0];
        typeSel.appendChild(opt);
      }
      typeSel.value = row.seriesType === 'anime' ? 'anime' : 'standard';

      const opts = optionsData || { profiles: [], rootFolders: [], defaultProfile: 9 };
      for (const profile of opts.profiles) {
        const opt = h('option', '', profileLabel(profile.name));
        opt.value = String(profile.id);
        profileSel.appendChild(opt);
      }
      const hasDefault = opts.profiles.some((p) => p.id === opts.defaultProfile);
      profileSel.value = String(hasDefault ? opts.defaultProfile : (opts.profiles[0] || {}).id || opts.defaultProfile);
      for (const root of opts.rootFolders) {
        const opt = h('option', '', root.path);
        opt.value = root.path;
        rootSel.appendChild(opt);
      }
      const syncRoot = () => {
        const profile = (optionsData ? optionsData.profiles : []).find((p) => String(p.id) === profileSel.value);
        const wantsAnime = typeSel.value === 'anime' || /anime/i.test((profile && profile.name) || '');
        const target = wantsAnime ? '/media/animes' : '/media/series';
        if ((optionsData ? optionsData.rootFolders : []).some((r) => r.path === target)) rootSel.value = target;
      };
      syncRoot();
      profileSel.addEventListener('change', syncRoot);
      typeSel.addEventListener('change', syncRoot);

      const addGo = btn('Adicionar e escolher episódios', 'hx-btn-primary', async () => {
        addGo.disabled = true;
        try {
          const data = await ordersApi('/sonarr/add', 'POST', {
            tvdbId: row.tvdbId,
            profileId: Number(profileSel.value),
            rootFolderPath: rootSel.value,
            seriesType: typeSel.value,
          });
          toast((data.alreadyExists ? 'Já estava no Sonarr: ' : 'Adicionado: ') + row.title);
          addResults.innerHTML = '';
          addInput.value = '';
          helpers.openEpisodes(data.series.id, !data.alreadyExists);
        } catch (e) {
          toast('Erro ao adicionar: ' + e.message, false);
        } finally {
          addGo.disabled = false;
        }
      });
      const field = (label, control) => {
        const wrap = h('label', 'hx-field');
        wrap.append(h('span', '', label), control);
        return wrap;
      };
      form.append(field('Perfil', profileSel), field('Pasta raiz', rootSel), field('Tipo', typeSel), addGo);
      main.appendChild(form);
    }

    box.appendChild(main);
    return box;
  }

  return { bar: addbar, body: addBody, open, show, close, setActive, loadOptions };
}
