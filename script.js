const listEl = document.getElementById('list');
const brandTabs = document.getElementById('brandTabs');

const BRANDS = [
    { id: 'ammo', label: 'Ammo by Mig' },
    { id: 'ammo_atom', label: 'ATOM (Ammo)' },
    { id: 'ak', label: 'AK Interactive' },
    { id: 'gunze', label: 'Gunze Sangyo' },
    { id: 'mr_hobby', label: 'Mr. Hobby' },
];

// Brand color mapping: brand display name -> hex color
const BRAND_COLORS = {
    'Ammo by Mig': '#FECC02',
    'Mr. Hobby': '#045AAA',
    'AK Interactive': '#E95A0E',
    'Gunze Sangyo': '#009DA5',
    'ATOM (Ammo)': '#0075C1',
};

// Map brand IDs to display names
const BRAND_NAME_MAP = {
    'ammo': 'Ammo by Mig',
    'ammo_atom': 'ATOM (Ammo)',
    'ak': 'AK Interactive',
    'gunze': 'Gunze Sangyo',
    'mr_hobby': 'Mr. Hobby',
};

// Global equivalents cache
let equivalentsData = null;

// Load equivalents once
async function loadEquivalents() {
    if (equivalentsData !== null) return equivalentsData;
    try {
        const res = await fetch('/data/equivalents.json');
        if (!res.ok) throw new Error('Failed to load equivalents');
        equivalentsData = await res.json();
        return equivalentsData;
    } catch (e) {
        console.warn('Equivalents not available:', e);
        equivalentsData = {};
        return equivalentsData;
    }
}

function createTabs() {
    brandTabs.innerHTML = '';
    BRANDS.forEach((b, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.dataset.brand = b.id;
        btn.className = 'px-3 py-1 rounded border text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 flex items-center gap-2';

        // Create color swatch
        const swatch = document.createElement('div');
        swatch.className = 'w-4 h-4 rounded-sm border border-gray-300 flex-shrink-0';
        swatch.style.backgroundColor = BRAND_COLORS[b.label] || '#cccccc';
        btn.appendChild(swatch);

        // Add label
        const label = document.createElement('span');
        label.textContent = b.label;
        btn.appendChild(label);

        const brandColor = BRAND_COLORS[b.label] || '#cccccc';

        btn.addEventListener('click', () => {
            // deactivate others
            [...brandTabs.children].forEach(ch => {
                ch.classList.remove('ring-2', 'ring-offset-2', 'text-white');
                ch.style.backgroundColor = '';
                ch.style.color = '';
            });
            // activate this one with brand color background
            btn.classList.add('ring-2', 'ring-offset-2');
            btn.style.backgroundColor = brandColor;
            btn.style.color = 'white';
            loadAndRender(b.id);
        });
        brandTabs.appendChild(btn);

        // select first by default
        if (idx === 0) {
            btn.classList.add('ring-2', 'ring-offset-2');
            btn.style.backgroundColor = brandColor;
            btn.style.color = 'white';
        }
    });
}

function storageKey(brand) {
    return `inStack:${brand}`;
}

function loadInStack(brand) {
    try {
        const raw = localStorage.getItem(storageKey(brand));
        return raw ? JSON.parse(raw) : {};
    } catch (e) {
        return {};
    }
}

function saveInStack(brand, map) {
    localStorage.setItem(storageKey(brand), JSON.stringify(map));
}

function renderRow(brand, color, inStackMap, displayBrand, equivalents) {
    const id = `${brand}:${color.code}`;
    const tpl = document.getElementById('colorRowTemplate');
    const node = tpl.content.firstElementChild.cloneNode(true);

    const swatch = node.querySelector('[data-swatch]');
    const codeEl = node.querySelector('[data-code]');
    const nameEl = node.querySelector('[data-name]');
    const btn = node.querySelector('[data-btn]');

    const hex = color.hex && String(color.hex).startsWith('#') ? color.hex : `#${color.hex || 'cccccc'}`;
    swatch.style.backgroundColor = hex;
    swatch.style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
    codeEl.textContent = `${color.code}`;
    nameEl.textContent = `${color.name}`;

    const checked = !!inStackMap[id];
    btn.textContent = checked ? 'In' : 'Add';
    if (checked) btn.classList.add('bg-green-100', 'dark:bg-green-900');

    btn.addEventListener('click', () => {
        if (inStackMap[id]) {
            delete inStackMap[id];
            btn.textContent = 'Add';
            btn.classList.remove('bg-green-100', 'dark:bg-green-900');
        } else {
            inStackMap[id] = true;
            btn.textContent = 'In';
            btn.classList.add('bg-green-100', 'dark:bg-green-900');
        }
        saveInStack(brand, inStackMap);
    });

    // show equivalents from separate file
    const eqEl = node.querySelector('[data-equivalents]');
    if (eqEl) {
        // Look up equivalents for this color from the equivalents data
        const eqs = (equivalents && equivalents[brand] && equivalents[brand][color.code]) || [];
        if (eqs.length) {
            eqEl.innerHTML = eqs.map(e => {
                const displayName = BRAND_NAME_MAP[e.brand] || e.brand;
                const brandColor = BRAND_COLORS[displayName] || '#cccccc';
                return `<div class="m-1 rounded px-2 py-0.5 text-xs font-medium text-white" style="background-color: ${brandColor};" title="${displayName}">${e.code}</div>`;
            }).join('');
        } else {
            eqEl.textContent = '';
        }
    }

    return node;
}

async function loadAndRender(brand) {
    listEl.innerHTML = '';
    try {
        let colors = [];
        let displayBrand = null;

        // Load equivalents first
        const equivalents = await loadEquivalents();

        // First, try loading from pack_[brand].json (unified format)
        let res = await fetch(`/data/pack_${brand}.json`).catch(() => null);

        if (res && res.ok) {
            const data = await res.json();
            colors = data.colors || [];
            displayBrand = data.brand || brand;
        } else if (brand === 'ammo_by_mig') {
            // Fallback for ammo_by_mig if pack file doesn't exist
            res = await fetch('/data/ammo_rows.json');
            if (!res.ok) throw new Error('Failed to load ammo rows');
            const rows = await res.json();
            // Convert rows to the expected color shape
            colors = rows.map(r => ({
                code: r.reference || r.code || '',
                name: r.name || '',
                hex: (r.hex || '').toString(),
                definition: r.definition || null,
                confidence: r.confidence || null
            }));
            displayBrand = 'Ammo by Mig';
        } else {
            throw new Error('Failed to load data');
        }

        const inStack = loadInStack(brand);
        colors.forEach(c => {
            const row = renderRow(brand, c, inStack, displayBrand, equivalents);
            listEl.appendChild(row);
        });
    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-red-500 dark:text-red-400">Unable to load data.</div>';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Preload equivalents data once
    loadEquivalents().then(() => {
        createTabs();
        // render first brand
        const first = BRANDS[0].id;
        loadAndRender(first);
    });
});
