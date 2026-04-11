const listEl = document.getElementById('list');
const brandTabs = document.getElementById('brandTabs');

// Display state
let showEquivalents = true;  // Default: show equivalents
let tableViewMode = false;   // Default: card view

const BRANDS = [
    { id: 'my-stack', label: 'My Stack' },
    { id: 'ammo', label: 'Ammo by Mig' },
    { id: 'ammo_atom', label: 'ATOM (Ammo)' },
    { id: 'ak', label: 'AK Interactive' },
    { id: 'gunze', label: 'Gunze Sangyo' },
    { id: 'tamiya', label: 'Tamiya' },
    { id: 'mr_hobby', label: 'Mr. Hobby' },
    { id: 'rlm', label: 'RLM' },
    { id: 'humbrol', label: 'Humbrol' },
    { id: 'vallejo', label: 'Vallejo' },
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
    "RLM": '#5C6B3A',
    "Humbrol": '#003087',
    "Vallejo": '#003d99',
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
    'rlm': 'RLM',
    'humbrol': 'Humbrol',
    'vallejo': 'Vallejo',
    "model_air": 'Vallejo Model Air',
    "model_color": 'Vallejo Model Color',
};

const EQUIVALENT_BRAND_MAP = {
    'HOBBY COLOR': 'Gunze Sangyo',
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

// ── Template Functions ────────────────────────────────────────────────────────

/**
 * Create a color card for the main grid view
 */
function createColorCardTemplate(brand, color, inStackMap, reverseEquivalentIndex) {
    const normalizedCode = normalizeEquivalentCode(color.code);
    const id = `${brand}:${normalizedCode}`;
    const hex = color.hex && String(color.hex).startsWith('#') ? color.hex : `#${color.hex || 'cccccc'}`;
    const checked = !!inStackMap[id];

    const div = document.createElement('div');
    div.className = 'bg-white dark:bg-gray-800 p-0 rounded-xl shadow-sm flex justify-between text-xl overflow-hidden';
    div.innerHTML = `
        <div class="w-12 shadow-sm flex-shrink-0" style="background-color: ${hex}; box-shadow: 0 2px 6px rgba(0,0,0,0.12)"></div>
        <div class="flex items-center gap-2 flex-1 p-2">
            <div class="flex-1 min-w-0">
                <div class="font-semibold text-xl truncate mb-0">${escapeHtml(color.code)}</div>
                <div class="font-semibold text-xs truncate mb-2">${escapeHtml(color.name || '')}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400"></div>
                <div class="equivalents text-xs text-gray-500 dark:text-gray-400${showEquivalents ? '' : ' hidden'}"></div>
                <div class="secondary-equivalents text-xs text-gray-500 dark:text-gray-400${showEquivalents ? '' : ' hidden'}"></div>
            </div>
            <button class="stack-btn px-2 py-0.5 rounded border text-xs whitespace-nowrap ${checked ? 'bg-green-100 dark:bg-green-900' : ''}">${checked ? 'In' : 'Add'}</button>
        </div>
    `;

    const btn = div.querySelector('.stack-btn');
    btn.dataset.colorId = id;
    btn.addEventListener('click', () => toggleColorInStack(brand, id, btn, inStackMap));

    const primaryEqEl = div.querySelector('.equivalents');
    const secondaryEqEl = div.querySelector('.secondary-equivalents');
    const primaryEquivalents = Array.isArray(color.equivalents) ? color.equivalents : [];
    const secondaryEquivalents = reverseEquivalentIndex.get(getColorKey(brand, color.code)) || [];

    renderEquivalentSection(primaryEqEl, 'Direct Equivalents', primaryEquivalents, 'primary');
    renderEquivalentSection(secondaryEqEl, 'Referenced By', secondaryEquivalents, 'secondary');

    return div;
}

/**
 * Create a stack item card for the sidebar or main view
 */
function createStackItemTemplate(brandId, code, color, brandColor, brandLabel, onRemove) {
    const hex = color ? color.hex : '#cccccc';
    const name = color ? color.name : '';

    const div = document.createElement('div');
    div.className = 'flex items-stretch bg-gray-50 dark:bg-gray-700 rounded-lg overflow-hidden shadow-sm';
    div.innerHTML = `
        <div class="w-8 flex-shrink-0" style="background-color: ${hex}"></div>
        <div class="flex-1 min-w-0 px-2 py-1">
            <div class="font-semibold text-xs truncate leading-tight">${escapeHtml(code)}</div>
            <div class="text-[10px] text-gray-400 dark:text-gray-400 truncate leading-tight">${escapeHtml(name)}</div>
            <div class="mt-0.5"><span class="text-[9px] px-1 py-0.5 rounded text-white leading-none" style="background-color: ${brandColor}">${escapeHtml(brandLabel)}</span></div>
        </div>
        <button class="remove-from-stack flex-shrink-0 text-gray-300 dark:text-gray-500 hover:text-red-400 px-1.5 text-base leading-none" title="Remove">×</button>
    `;

    const removeBtn = div.querySelector('.remove-from-stack');
    removeBtn.dataset.brandId = brandId;
    removeBtn.dataset.code = code;
    removeBtn.addEventListener('click', onRemove);

    return div;
}

/**
 * Create a large stack card for full-screen view
 */
function createStackCardLargeTemplate(brandId, code, color, brandColor, brandLabel, onRemove) {
    const hex = color ? color.hex : '#cccccc';
    const name = color ? color.name : '';

    const div = document.createElement('div');
    div.className = 'bg-white dark:bg-gray-800 rounded-xl shadow-md overflow-hidden flex flex-col sm:flex-row hover:shadow-lg transition-shadow';
    div.innerHTML = `
        <div class="w-20 h-20 sm:w-24 sm:h-24 flex-shrink-0" style="background-color: ${hex}"></div>
        <div class="flex-1 p-4 flex flex-col justify-center">
            <div class="font-bold text-lg">${escapeHtml(code)}</div>
            <div class="text-sm text-gray-600 dark:text-gray-300 mt-1">${escapeHtml(name)}</div>
            <div class="mt-2"><span class="text-xs px-2 py-1 rounded text-white" style="background-color: ${brandColor}">${escapeHtml(brandLabel)}</span></div>
        </div>
        <button class="remove-from-stack flex-shrink-0 flex items-center justify-center w-12 h-12 text-gray-300 dark:text-gray-500 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900 text-2xl" title="Remove">×</button>
    `;

    const removeBtn = div.querySelector('.remove-from-stack');
    removeBtn.dataset.brandId = brandId;
    removeBtn.dataset.code = code;
    removeBtn.addEventListener('click', onRemove);

    return div;
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * Toggle a color in the stack
 */
function toggleColorInStack(brand, id, btn, inStackMap) {
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
    renderStackPanel();

    // Refresh equivalent badges to show/hide checkmarks
    updateEquivalentBadges();
}

/**
 * Update all equivalent badges on the page to reflect current stack state
 */
function updateEquivalentBadges() {
    const badges = document.querySelectorAll('[data-eq-brand][data-eq-code]');
    badges.forEach(badge => {
        const brandId = badge.dataset.eqBrand;
        const code = badge.dataset.eqCode;
        const inStack = isColorInStack(brandId, code);
        const currentTitle = badge.getAttribute('title') || '';
        const displayName = currentTitle.replace(' (in stack)', '').trim();

        if (inStack) {
            // Add ring and checkmark
            badge.classList.add('ring-2', 'ring-offset-1', 'ring-yellow-300', 'dark:ring-yellow-500');
            badge.setAttribute('title', displayName + ' (in stack)');
            // Ensure checkmark is present
            if (!badge.textContent.includes('✓')) {
                const currentText = badge.textContent || '';
                badge.textContent = currentText.trim() + ' ✓';
            }
        } else {
            // Remove ring and checkmark
            badge.classList.remove('ring-2', 'ring-offset-1', 'ring-yellow-300', 'dark:ring-yellow-500');
            badge.setAttribute('title', displayName);
            // Remove checkmark if present
            if (badge.textContent.includes('✓')) {
                badge.textContent = badge.textContent.replace(/\s✓\s*$/, '').trim();
            }
        }
    });
}

// Global lookup: "brandId:NORMALIZEDCODE" -> {hex, name, code, brandId}
const colorLookup = new Map();

function addToColorLookup(pack) {
    if (!pack) return;
    const brandId = pack.brand_id || normalizeBrandId(pack.brand);
    (pack.colors || []).forEach(c => {
        const key = `${brandId}:${normalizeEquivalentCode(c.code)}`;
        if (!colorLookup.has(key)) {
            const hex = c.hex ? (String(c.hex).startsWith('#') ? c.hex : `#${c.hex}`) : '#cccccc';
            colorLookup.set(key, { hex, name: c.name || '', code: c.code || '', brandId });
        }
    });
}

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
    const eqBrandId = normalizeBrandId(item.brand);
    const eqCode = normalizeEquivalentCode(item.code);

    // Check if this equivalent is in the stack
    const inStack = isColorInStack(eqBrandId, eqCode);
    const badgeClass = inStack ? 'ring-2 ring-offset-1 ring-yellow-300 dark:ring-yellow-500' : '';
    const checkIcon = inStack ? ' ✓' : '';

    return `<div class="m-1 rounded px-2 py-0.5 text-xs font-medium text-white cursor-default ${badgeClass}" style="background-color: ${brandColor}" title="${displayName}${inStack ? ' (in stack)' : ''}" data-eq-brand="${eqBrandId}" data-eq-code="${eqCode}">${label}${checkIcon}</div>`;
}

function renderEquivalentSection(container, title, items, tone) {
    if (!container) return;

    if (!items.length || !showEquivalents) {
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
    const res = await fetch(`./data/pack_${brand}.json`).catch(() => null);

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
    addToColorLookup(pack);
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

        // Create color swatch (skip for My Stack tab)
        if (b.id !== 'my-stack') {
            const swatch = document.createElement('div');
            swatch.className = 'w-4 h-4 rounded-sm border border-gray-300 flex-shrink-0';
            swatch.style.backgroundColor = BRAND_COLORS[b.label] || '#cccccc';
            btn.appendChild(swatch);
        }

        // Add label
        const label = document.createElement('span');
        label.textContent = b.label;
        btn.appendChild(label);

        const brandColor = b.id === 'my-stack' ? '#ec4899' : (BRAND_COLORS[b.label] || '#cccccc');

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
        if (idx === 0 && b.id !== 'my-stack') {
            btn.classList.add('ring-2', 'ring-offset-2');
            btn.style.backgroundColor = brandColor;
            btn.style.color = 'white';
        }
    });
}

function storageKey(brand) {
    return `inStack:${brand}`;
}

/**
 * Check if a color (by brand and code) is in any stack
 */
function isColorInStack(brandId, code) {
    const map = loadInStack(brandId);
    const normalizedCode = normalizeEquivalentCode(code);
    const key = `${brandId}:${normalizedCode}`;
    return !!map[key];
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
    return createColorCardTemplate(brand, color, inStackMap, reverseEquivalentIndex);
}

let currentSort = 'code-asc';

function sortColors(colors) {
    if (currentSort === 'default') return colors;


    return [...colors].sort((a, b) => {
        const numA = parseFloat(String(a.code).replace(/[^0-9.]/g, ''));
        const numB = parseFloat(String(b.code).replace(/[^0-9.]/g, ''));
        if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
        return String(a.code).localeCompare(String(b.code), undefined, { sensitivity: 'base' });
    });

}

async function loadAndRender(brand) {
    // Handle My Stack tab
    if (brand === 'my-stack') {
        await renderStackViewFullScreen();
        return;
    }

    listEl.innerHTML = '';
    try {
        const [data, reverseEquivalentIndex] = await Promise.all([
            loadPack(brand),
            getReverseEquivalentIndex(),
        ]);

        if (!data) {
            throw new Error('Failed to load data');
        }

        const colors = sortColors(data.colors || []);
        const displayBrand = data.brand || brand;

        const inStack = loadInStack(brand);

        if (tableViewMode) {
            renderTableView(colors, brand, inStack, reverseEquivalentIndex);
        } else {
            colors.forEach(c => {
                const row = renderRow(brand, c, inStack, displayBrand, reverseEquivalentIndex);
                listEl.appendChild(row);
            });
        }
    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-red-500 dark:text-red-400">Unable to load data.</div>';
    }
}

function renderTableView(colors, brand, inStack, reverseEquivalentIndex) {
    // Create a table structure for card grid view
    listEl.className = 'space-y-0 border border-gray-200 dark:border-gray-700 rounded overflow-hidden';

    // Table header
    const headerRow = document.createElement('div');
    headerRow.className = 'grid gap-0 bg-gray-100 dark:bg-gray-700 rounded-none border-b border-gray-200 dark:border-gray-700';

    if (showEquivalents) {
        headerRow.style.gridTemplateColumns = '40px 80px 1fr 200px 80px';
        headerRow.innerHTML = `
            <div class="p-2"></div>
            <div class="p-2 font-semibold text-sm border-r border-gray-200 dark:border-gray-700">Code</div>
            <div class="p-2 font-semibold text-sm border-r border-gray-200 dark:border-gray-700">Name</div>
            <div class="p-2 font-semibold text-sm border-r border-gray-200 dark:border-gray-700">Equivalents</div>
            <div class="p-2 font-semibold text-sm">Stack</div>
        `;
    } else {
        headerRow.style.gridTemplateColumns = '40px 80px 1fr 80px';
        headerRow.innerHTML = `
            <div class="p-2"></div>
            <div class="p-2 font-semibold text-sm border-r border-gray-200 dark:border-gray-700">Code</div>
            <div class="p-2 font-semibold text-sm border-r border-gray-200 dark:border-gray-700">Name</div>
            <div class="p-2 font-semibold text-sm">Stack</div>
        `;
    }

    listEl.appendChild(headerRow);

    // Table rows
    colors.forEach((color, idx) => {
        const normalizedCode = normalizeEquivalentCode(color.code);
        const id = `${brand}:${normalizedCode}`;
        const hex = color.hex && String(color.hex).startsWith('#') ? color.hex : `#${color.hex || 'cccccc'}`;
        const checked = !!inStack[id];

        const row = document.createElement('div');
        row.className = 'grid gap-0 items-center border-b border-gray-200 dark:border-gray-700 last:border-b-0';

        if (showEquivalents) {
            row.style.gridTemplateColumns = '40px 80px 1fr 200px 80px';
        } else {
            row.style.gridTemplateColumns = '40px 80px 1fr 80px';
        }

        // Swatch
        const swatchCol = document.createElement('div');
        swatchCol.className = 'h-12 rounded-none border-r border-gray-200 dark:border-gray-700';
        swatchCol.style.backgroundColor = hex;
        swatchCol.style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
        row.appendChild(swatchCol);

        // Code
        const codeCol = document.createElement('div');
        codeCol.className = 'p-2 font-semibold text-sm truncate border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';
        codeCol.textContent = color.code;
        row.appendChild(codeCol);

        // Name
        const nameCol = document.createElement('div');
        nameCol.className = 'p-2 text-sm truncate border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';
        nameCol.textContent = color.name;
        row.appendChild(nameCol);

        // Equivalents
        if (showEquivalents) {
            const eqCol = document.createElement('div');
            eqCol.className = 'p-2 flex flex-wrap gap-1 overflow-y-auto border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 max-h-12';
            const primaryEquivalents = Array.isArray(color.equivalents) ? color.equivalents : [];
            eqCol.innerHTML = primaryEquivalents.slice(0, 2).map(item => renderEquivalentBadge(item, 'primary')).join('');
            if (primaryEquivalents.length > 2) {
                const more = document.createElement('span');
                more.className = 'text-[10px] text-gray-500 dark:text-gray-400';
                more.textContent = `+${primaryEquivalents.length - 2}`;
                eqCol.appendChild(more);
            }
            row.appendChild(eqCol);
        }

        // Stack button
        const btnCol = document.createElement('div');
        btnCol.className = 'p-2 bg-white dark:bg-gray-800';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `px-2 py-1 rounded border text-xs whitespace-nowrap w-full text-gray-800 dark:text-gray-100 ${checked ? 'bg-green-100 dark:bg-green-900 border-green-300 dark:border-green-700' : 'bg-gray-50 dark:bg-gray-700 border-gray-300 dark:border-gray-600'}`;
        btn.textContent = checked ? 'In' : 'Add';
        btn.dataset.colorId = id;
        btn.addEventListener('click', () => {
            if (inStack[id]) {
                delete inStack[id];
                btn.textContent = 'Add';
                btn.classList.remove('bg-green-100', 'dark:bg-green-900', 'border-green-300', 'dark:border-green-700');
                btn.classList.add('bg-gray-50', 'dark:bg-gray-700', 'border-gray-300', 'dark:border-gray-600');
            } else {
                inStack[id] = true;
                btn.textContent = 'In';
                btn.classList.remove('bg-gray-50', 'dark:bg-gray-700', 'border-gray-300', 'dark:border-gray-600');
                btn.classList.add('bg-green-100', 'dark:bg-green-900', 'border-green-300', 'dark:border-green-700');
            }
            saveInStack(brand, inStack);
            renderStackPanel();
            updateEquivalentBadges();
        });
        btnCol.appendChild(btn);
        row.appendChild(btnCol);

        listEl.appendChild(row);
    });
}

// ── Tooltip ──────────────────────────────────────────────────────────────────

function setupTooltip() {
    const tooltip = document.getElementById('colorTooltip');
    const swatchEl = document.getElementById('tooltipSwatch');
    const codeEl = document.getElementById('tooltipCode');
    const nameEl = document.getElementById('tooltipName');
    const brandEl = document.getElementById('tooltipBrand');

    document.addEventListener('mouseover', e => {
        const badge = e.target.closest('[data-eq-brand]');
        if (!badge) return;

        const brandId = badge.dataset.eqBrand;
        const code = badge.dataset.eqCode;
        const color = colorLookup.get(`${brandId}:${code}`);

        if (!color) {
            // Kick off a background load so future hovers resolve
            loadPack(brandId).catch(() => { });
            tooltip.classList.add('hidden');
            return;
        }

        swatchEl.style.backgroundColor = color.hex;
        codeEl.textContent = color.code;
        nameEl.textContent = color.name;
        brandEl.textContent = BRAND_NAME_MAP[color.brandId] || color.brandId;

        const rect = badge.getBoundingClientRect();
        const tipW = 176; // w-44 = 11rem = 176px
        const tipH = 96;
        let top = rect.bottom + 6;
        let left = rect.left;
        if (top + tipH > window.innerHeight - 8) top = rect.top - tipH - 6;
        if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
        if (left < 8) left = 8;
        tooltip.style.top = `${top}px`;
        tooltip.style.left = `${left}px`;
        tooltip.classList.remove('hidden');
    });

    document.addEventListener('mouseout', e => {
        const badge = e.target.closest('[data-eq-brand]');
        if (badge) tooltip.classList.add('hidden');
    });
}

// ── Stack helpers ─────────────────────────────────────────────────────────────

function getAllStackedColors() {
    const items = [];
    BRANDS.forEach(b => {
        const map = loadInStack(b.id);
        Object.keys(map).filter(k => map[k]).forEach(key => {
            const idx = key.indexOf(':');
            if (idx < 0) return;
            items.push({ brandId: key.slice(0, idx), code: key.slice(idx + 1) });
        });
    });
    return items;
}

function saveStackToFile() {
    const items = getAllStackedColors();
    if (!items.length) {
        alert('Your stack is empty.');
        return;
    }
    // Save only the codes (just the code part, not brand:code)
    const content = items.map(i => i.code).join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'my-color-stack.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function loadStackFromFile(file) {
    const reader = new FileReader();
    reader.onload = e => {
        const lines = e.target.result.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
        const brandMaps = {};
        let loadedCount = 0;

        lines.forEach(line => {
            // Support both formats: brandId:code or just code
            let brandId, code;
            const idx = line.indexOf(':');

            if (idx > 0) {
                // Format: brandId:code
                brandId = line.slice(0, idx);
                code = line.slice(idx + 1);
            } else {
                // Format: just code - search across all brands
                code = line;
                // Find which brand(s) have this code
                for (const [bId, color] of colorLookup) {
                    if (color.code.toUpperCase() === code.toUpperCase()) {
                        brandId = color.brandId;
                        break;
                    }
                }
            }

            if (brandId && code) {
                if (!brandMaps[brandId]) brandMaps[brandId] = loadInStack(brandId);
                const normalizedCode = normalizeEquivalentCode(code);
                brandMaps[brandId][`${brandId}:${normalizedCode}`] = true;
                loadedCount++;
            }
        });

        Object.entries(brandMaps).forEach(([brandId, map]) => saveInStack(brandId, map));
        renderStackPanel();
        alert(`Loaded ${loadedCount} color${loadedCount !== 1 ? 's' : ''} into your stack.`);
    };
    reader.readAsText(file);
}

// ── View mode management ──────────────────────────────────────────────────────

/**
 * Update UI to reflect current view mode
 */
async function renderStackPanel() {
    // Update the My Stack tab if it's currently active
    const activeTab = document.querySelector('[data-brand].ring-2');
    if (activeTab && activeTab.dataset.brand === 'my-stack') {
        await renderStackViewFullScreen();
    }
}

/**
 * Handle removing a color from the stack
 */
function handleRemoveFromStack(e, brandId, code) {
    const map = loadInStack(brandId);
    delete map[`${brandId}:${code}`];
    saveInStack(brandId, map);
    // Sync the Add/In button on the main list if visible
    const mainBtn = document.querySelector(`[data-color-id="${brandId}:${code}"]`);
    if (mainBtn) {
        mainBtn.textContent = 'Add';
        mainBtn.classList.remove('bg-green-100', 'dark:bg-green-900');
    }
    renderStackPanel();

    // Refresh equivalent badges to show/hide checkmarks
    updateEquivalentBadges();

    // Re-render stack view if currently displayed
    const activeTab = document.querySelector('[data-brand].ring-2');
    if (activeTab && activeTab.dataset.brand === 'my-stack') {
        renderStackViewFullScreen();
    }
}

// ── Stack Full-Screen View ────────────────────────────────────────────────────

/**
 * Render the stack in the main content area
 */
async function renderStackViewFullScreen() {
    // Load all data if needed
    const items = getAllStackedColors();
    const brandIds = [...new Set(items.map(i => i.brandId))];
    await Promise.all(brandIds.map(id => loadPack(id).catch(() => null)));

    listEl.innerHTML = '';

    if (!items.length) {
        listEl.className = 'flex items-center justify-center min-h-96';
        listEl.innerHTML = `
            <div class="text-center">
                <div class="text-2xl font-bold text-gray-400 dark:text-gray-500 mb-4">Your Stack is Empty</div>
                <p class="text-gray-500 dark:text-gray-400 mb-6">Add colors to your stack using the <strong>Add</strong> button on color cards.</p>
            </div>
        `;
        return;
    }

    // Create wrapper for stack items with action buttons
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full space-y-4';

    // Action buttons at top
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'flex gap-2';

    const saveBtn = document.createElement('button');
    saveBtn.id = 'btnSaveStack';
    saveBtn.textContent = 'Save to file';
    saveBtn.className = 'px-3 py-1.5 rounded border text-xs bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-100 dark:hover:bg-gray-600';
    saveBtn.addEventListener('click', saveStackToFile);
    buttonContainer.appendChild(saveBtn);

    const loadLabel = document.createElement('label');
    loadLabel.className = 'px-3 py-1.5 rounded border text-xs bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer';
    loadLabel.textContent = 'Load from file';
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.id = 'stackFileInput';
    fileInput.accept = '.txt';
    fileInput.className = 'hidden';
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            loadStackFromFile(file);
            e.target.value = '';
        }
    });
    loadLabel.appendChild(fileInput);
    buttonContainer.appendChild(loadLabel);

    wrapper.appendChild(buttonContainer);

    // Grid container for stack items
    const gridContainer = document.createElement('div');
    gridContainer.className = 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4 w-full';

    items.forEach(({ brandId, code }) => {
        const key = `${brandId}:${normalizeEquivalentCode(code)}`;
        const color = colorLookup.get(key);
        const inStack = loadInStack(brandId);
        const displayBrand = BRAND_NAME_MAP[brandId] || brandId;

        // Use the same template as for color browsing
        const card = createColorCardTemplate(brandId, color, inStack, new Map());
        gridContainer.appendChild(card);
    });

    wrapper.appendChild(gridContainer);
    listEl.appendChild(wrapper);
}

// ── My Stack modal (legacy) ───────────────────────────────────────────────────

async function showMyStack() {
    const modal = document.getElementById('myStackModal');
    const grid = document.getElementById('stackGrid');
    modal.classList.remove('hidden');
    grid.innerHTML = '<div class="col-span-full text-sm text-gray-500 py-4 text-center">Loading…</div>';

    // Ensure all packs (and colorLookup) are populated
    await Promise.all(BRANDS.map(b => loadPack(b.id).catch(() => null)));

    const items = getAllStackedColors();
    if (!items.length) {
        grid.innerHTML = '<div class="col-span-full text-sm text-gray-500 py-8 text-center">Your stack is empty. Add colors using the <strong>Add</strong> button on each color card.</div>';
        return;
    }

    grid.innerHTML = '';
    items.forEach(({ brandId, code }) => {
        const color = colorLookup.get(`${brandId}:${normalizeEquivalentCode(code)}`);
        const hex = color ? color.hex : '#cccccc';
        const name = color ? color.name : '';
        const brandLabel = BRAND_NAME_MAP[brandId] || brandId;
        const brandColor = BRAND_COLORS[BRAND_NAME_MAP[brandId]] || '#6b7280';

        const card = document.createElement('div');
        card.className = 'bg-white dark:bg-gray-700 rounded-xl shadow overflow-hidden flex';
        card.innerHTML = `
            <div class="w-10 flex-shrink-0" style="background-color:${hex}"></div>
            <div class="p-2 min-w-0 flex-1">
                <div class="font-semibold text-sm truncate">${code}</div>
                <div class="text-xs text-gray-500 dark:text-gray-300 truncate leading-tight">${name}</div>
                <div class="mt-1"><span class="text-[10px] px-1 py-0.5 rounded text-white" style="background-color:${brandColor}">${brandLabel}</span></div>
            </div>`;
        grid.appendChild(card);
    });
}

// ── All Colors view ──────────────────────────────────────────────────────────

function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : { r: 0, g: 0, b: 0 };
}

function hexToHsl(hex) {
    const { r, g, b } = hexToRgb(hex);
    const rp = r / 255, gp = g / 255, bp = b / 255;
    const max = Math.max(rp, gp, bp), min = Math.min(rp, gp, bp);
    let h, s, l = (max + min) / 2;

    if (max === min) {
        h = s = 0;
    } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case rp: h = (gp - bp) / d + (gp < bp ? 6 : 0); break;
            case gp: h = (bp - rp) / d + 2; break;
            case bp: h = (rp - gp) / d + 4; break;
        }
        h /= 6;
    }
    return { h: h * 360, s: s * 100, l: l * 100 };
}

async function showAllColors() {
    const modal = document.getElementById('allColorsModal');
    const list = document.getElementById('allColorsList');

    modal.classList.remove('hidden');
    list.innerHTML = '<div class="col-span-full text-center py-8">Loading all colors...</div>';

    // Load all packs
    await Promise.all(BRANDS.map(b => loadPack(b.id).catch(() => null)));

    // Collect all colors with brand info
    const allColors = [];
    for (const [key, color] of colorLookup) {
        allColors.push({
            ...color,
            key: key,
        });
    }

    // Sort by HSL hue then lightness (for natural color order)
    allColors.sort((a, b) => {
        const hslA = hexToHsl(a.hex);
        const hslB = hexToHsl(b.hex);
        // Sort by hue primarily, then by lightness
        if (Math.abs(hslA.h - hslB.h) > 5) return hslA.h - hslB.h;
        return hslA.l - hslB.l;
    });

    // Render
    list.innerHTML = '';
    allColors.forEach(color => {
        const card = document.createElement('div');
        card.className = 'group';
        card.innerHTML = `
            <div class="flex overflow-hidden">
                <div class="w-20 h-10" style="background-color: ${color.hex}"></div>
                <div class="p-2 bg-white dark:bg-gray-700 text-xs">
                    <div class="font-semibold truncate">${color.code} ${color.name}</div>
                </div>
            </div>
        `;


        list.appendChild(card);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    createTabs();
    setupTooltip();



    document.getElementById('btnAllColors').addEventListener('click', showAllColors);
    document.getElementById('closeAllColors').addEventListener('click', () => {
        document.getElementById('allColorsModal').classList.add('hidden');
    });

    // Toggle equivalents visibility
    document.getElementById('btnToggleEquivalents').addEventListener('click', (e) => {
        showEquivalents = !showEquivalents;
        const btn = e.target;
        btn.textContent = showEquivalents ? 'Hide Equivalents' : 'Show Equivalents';
        if (!showEquivalents) {
            btn.classList.remove('bg-blue-100', 'dark:bg-blue-900', 'text-blue-900', 'dark:text-blue-100');
            btn.classList.add('bg-gray-200', 'dark:bg-gray-700', 'text-gray-700', 'dark:text-gray-300');
        } else {
            btn.classList.add('bg-blue-100', 'dark:bg-blue-900', 'text-blue-900', 'dark:text-blue-100');
            btn.classList.remove('bg-gray-200', 'dark:bg-gray-700', 'text-gray-700', 'dark:text-gray-300');
        }
        // Re-render current view
        const activeTab = document.querySelector('[data-brand].ring-2');
        if (activeTab) {
            loadAndRender(activeTab.dataset.brand);
        }
    });

    // Toggle table/card view
    document.getElementById('btnToggleView').addEventListener('click', (e) => {
        tableViewMode = !tableViewMode;
        const btn = e.target;
        btn.textContent = tableViewMode ? 'Card View' : 'Table View';
        if (tableViewMode) {
            btn.classList.remove('bg-green-100', 'dark:bg-green-900', 'text-green-900', 'dark:text-green-100');
            btn.classList.add('bg-yellow-100', 'dark:bg-yellow-900', 'text-yellow-900', 'dark:text-yellow-100');
        } else {
            btn.classList.remove('bg-yellow-100', 'dark:bg-yellow-900', 'text-yellow-900', 'dark:text-yellow-100');
            btn.classList.add('bg-green-100', 'dark:bg-green-900', 'text-green-900', 'dark:text-green-100');
        }
        // Reset list styling and re-render
        listEl.className = tableViewMode ? 'space-y-0' : 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 shadow-sm';
        // Re-render current view
        const activeTab = document.querySelector('[data-brand].ring-2');
        if (activeTab) {
            loadAndRender(activeTab.dataset.brand);
        }
    });

    // render first brand
    const first = BRANDS[0].id;
    listEl.className = 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 shadow-sm';
    loadAndRender(first);
});
