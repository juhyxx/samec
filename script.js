const listEl = document.getElementById('list');
const brandTabs = document.getElementById('brandTabs');

const BRANDS = [
    { id: 'ammo', label: 'Ammo by Mig' },
    { id: 'ammo_atom', label: 'ATOM (Ammo)' },
    { id: 'ak', label: 'AK Interactive' },
    { id: 'gunze', label: 'Gunze Sangyo' },
    { id: 'tamiya', label: 'Tamiya' },
    { id: 'mr_hobby', label: 'Mr. Hobby' },
];

// Brand color mapping: brand display name -> hex color
const BRAND_COLORS = {
    'Ammo by Mig': '#FECC02',
    'Mr. Hobby': '#045AAA',
    'AK Interactive': '#E95A0E',
    'Gunze Sangyo': '#009DA5',
    'ATOM (Ammo)': '#0075C1',
    "Federal Standard": '#A6192E',
    "Tamiya": '#004B87',
    "RAL": '#A6192E',
    "Vallejo Model Air": '#05E2E1',
    "Vallejo Model Color": '#05E2E1',
};

// Map brand IDs to display names
const BRAND_NAME_MAP = {
    'ammo': 'Ammo by Mig',
    'ammo_atom': 'ATOM (Ammo)',
    'ak': 'AK Interactive',
    'gunze': 'Gunze Sangyo',
    'federal_standard': 'Federal Standard',
    'tamiya': 'Tamiya',
    'mr_hobby': 'Mr. Hobby',
    'ral': 'RAL',
    "model_air": 'Vallejo Model Air',
    "model_color": 'Vallejo Model Color',
};

const EQUIVALENT_BRAND_MAP = {
    'HOBBY COLOR': 'Mr. Hobby',
    'MR.COLOR': 'Mr. Hobby',
    'TAMIYA': 'Tamiya',
    'RAL': 'RAL',
    'FEDERAL STANDARD': 'Federal Standard',
    'FS': 'Federal Standard',
    'MODEL AIR': 'Vallejo Model Air',
    'MODEL COLOR': 'Vallejo Model Color',
    'AK INTERACTIVE': 'AK Interactive',
    'GUNZE SANGYO': 'Gunze Sangyo',
    'AMMO BY MIG': 'Ammo by Mig',
    'AMMO BY MIG ATOM': 'ATOM (Ammo)',
};

const PACK_CACHE = new Map();
let reverseEquivalentIndexPromise = null;

function getEquivalentDisplayName(brand) {
    if (!brand) return '';

    const mappedById = BRAND_NAME_MAP[brand];
    if (mappedById) return mappedById;

    const upper = String(brand).toUpperCase();
    return EQUIVALENT_BRAND_MAP[upper] || brand;
}

function normalizeBrandId(brand) {
    if (!brand) return '';

    const raw = String(brand).trim();
    const mappedName = BRAND_NAME_MAP[raw] || EQUIVALENT_BRAND_MAP[raw.toUpperCase()] || raw;

    const entry = BRANDS.find(item => item.label === mappedName || item.id === raw);
    if (entry) return entry.id;

    const normalized = mappedName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');

    if (normalized === 'ammo_by_mig') return 'ammo';
    if (normalized === 'atom_ammo') return 'ammo_atom';
    if (normalized === 'gunze_mr_hobby') return 'gunze';
    if (normalized === 'federal_standard') return 'federal_standard';
    return normalized;
}

function normalizeEquivalentCode(code) {
    if (!code) return '';
    return String(code)
        .trim()
        .toUpperCase()
        .replace(/\s+/g, '')
        .replace(/_/g, '')
        .replace(/-/g, '');
}

function getColorKey(brand, code) {
    return `${normalizeBrandId(brand)}:${normalizeEquivalentCode(code)}`;
}

function renderEquivalentBadge(item, tone) {
    const displayName = getEquivalentDisplayName(item.brand);
    const brandColor = BRAND_COLORS[displayName] || '#6b7280';


    const label = item.code;

    return `<div class="m-1 rounded px-2 py-0.5 text-xs font-medium text-white" style="background-color: ${brandColor}" title="${displayName}">${label}</div>`;
}

function renderEquivalentSection(container, title, items, tone) {
    if (!container) return;

    if (!items.length) {
        container.innerHTML = '';
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    container.innerHTML = `
        <div class="mt-2">
            <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">${title}</div>
            <div class="flex flex-wrap">${items.map(item => renderEquivalentBadge(item, tone)).join('')}</div>
        </div>
    `;
}

async function loadPack(brand) {
    if (PACK_CACHE.has(brand)) {
        return PACK_CACHE.get(brand);
    }

    let pack = null;
    const res = await fetch(`/data/pack_${brand}.json`).catch(() => null);

    if (res && res.ok) {
        pack = await res.json();
    } else if (brand === 'ammo_by_mig') {
        const fallback = await fetch('/data/ammo_rows.json');
        if (!fallback.ok) throw new Error('Failed to load ammo rows');
        const rows = await fallback.json();
        pack = {
            brand: 'Ammo by Mig',
            brand_id: 'ammo',
            colors: rows.map(r => ({
                code: r.reference || r.code || '',
                name: r.name || '',
                hex: (r.hex || '').toString(),
                definition: r.definition || null,
                confidence: r.confidence || null,
                equivalents: Array.isArray(r.equivalents) ? r.equivalents : [],
            })),
        };
    }

    PACK_CACHE.set(brand, pack);
    return pack;
}

async function getReverseEquivalentIndex() {
    if (!reverseEquivalentIndexPromise) {
        reverseEquivalentIndexPromise = (async () => {
            const index = new Map();
            const packs = await Promise.all(
                BRANDS.map(async entry => {
                    try {
                        return await loadPack(entry.id);
                    } catch (error) {
                        console.error(`Failed to build reverse equivalents for ${entry.id}`, error);
                        return null;
                    }
                })
            );

            packs.filter(Boolean).forEach(pack => {
                const sourceBrand = pack.brand_id || normalizeBrandId(pack.brand);
                (pack.colors || []).forEach(color => {
                    const outgoing = Array.isArray(color.equivalents) ? color.equivalents : [];
                    outgoing.forEach(eq => {
                        const targetKey = getColorKey(eq.brand, eq.code);
                        if (!targetKey || targetKey.endsWith(':')) return;

                        if (!index.has(targetKey)) {
                            index.set(targetKey, []);
                        }

                        index.get(targetKey).push({
                            brand: getEquivalentDisplayName(sourceBrand),
                            code: color.code,
                            name: color.name,
                        });
                    });
                });
            });

            return index;
        })();
    }

    return reverseEquivalentIndexPromise;
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

function renderRow(brand, color, inStackMap, displayBrand, reverseEquivalentIndex) {
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

    // Show equivalents embedded in the pack JSON.
    const primaryEqEl = node.querySelector('[data-equivalents]');
    const secondaryEqEl = node.querySelector('[data-secondary-equivalents]');
    const primaryEquivalents = Array.isArray(color.equivalents) ? color.equivalents : [];
    const secondaryEquivalents = reverseEquivalentIndex.get(getColorKey(brand, color.code)) || [];

    renderEquivalentSection(primaryEqEl, 'Direct Equivalents', primaryEquivalents, 'primary');
    renderEquivalentSection(secondaryEqEl, 'Referenced By', secondaryEquivalents, 'secondary');

    return node;
}

async function loadAndRender(brand) {
    listEl.innerHTML = '';
    try {
        const [data, reverseEquivalentIndex] = await Promise.all([
            loadPack(brand),
            getReverseEquivalentIndex(),
        ]);

        if (!data) {
            throw new Error('Failed to load data');
        }

        const colors = data.colors || [];
        const displayBrand = data.brand || brand;

        const inStack = loadInStack(brand);
        colors.forEach(c => {
            const row = renderRow(brand, c, inStack, displayBrand, reverseEquivalentIndex);
            listEl.appendChild(row);
        });
    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-red-500 dark:text-red-400">Unable to load data.</div>';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    createTabs();
    // render first brand
    const first = BRANDS[0].id;
    loadAndRender(first);
});
