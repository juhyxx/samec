const listEl = document.getElementById('list');
const brandTabs = document.getElementById('brandTabs');

// Display state
let showEquivalents = true;  // Default: show equivalents

const BRANDS = [
    { id: 'my-stack', label: 'My Stack' },
    { id: 'ammo', label: 'Ammo by Mig' },
    { id: 'ammo_atom', label: 'ATOM (Ammo)' },
    { id: 'ak', label: 'AK Interactive' },
    { id: 'gunze', label: 'Aqueous Hobby color' },
    { id: 'mr_hobby', label: 'Mr. Color' },
    { id: 'vallejo', label: 'Vallejo' },
    { id: 'tamiya', label: 'Tamiya' },
    { id: 'humbrol', label: 'Humbrol' },
    { id: 'rlm', label: 'RLM' },
];

// Map brand display names to colors (used for equivalent badges and button backgrounds)
const BRAND_BADGE_COLORS = {
    'Ammo by Mig': '#FECC02',
    'Mr. Color': '#045AAA',
    'AK Interactive': '#E95A0E',
    'Aqueous Hobby color': '#009DA5',
    'ATOM (Ammo)': '#0075C1',
    "Federal Standard": '#A6192E',
    "Tamiya": '#004B87',
    "RAL": '#A6192E',
    "RLM": '#5C6B3A',
    "Humbrol": '#003087',
    "Vallejo": '#05E2E1',
    "Vallejo Model Air": '#05E2E1',
    "Vallejo Model Color": '#05E2E1',
};

// Map brand ID to logo color (for fallback)
const BRAND_LOGO_COLORS = {
    'my-stack': '#ec4899',
    'ammo': '#FECC02',
    'ammo_atom': '#0075C1',
    'ak': '#E95A0E',
    'gunze': '#009DA5',
    'tamiya': '#004B87',
    'mr_hobby': '#045AAA',
    'rlm': '#5C6B3A',
    'humbrol': '#F04A40',
    'vallejo': '#05E2E1',
};

// Map brand IDs to logo filenames (for special cases)
const BRAND_LOGO_FILES = {
    'ammo_atom': 'ammo',  // ammo_atom uses ammo logo
    'mr_hobby': 'mrhobby',  // mr_hobby PNG is named mrhobby.png
    "gunze": "mrhobby", // gunze uses mr_hobby logo
};

// Map brand IDs to display names
const BRAND_NAME_MAP = {
    'ammo': 'Ammo by Mig',
    'ammo_atom': 'ATOM (Ammo)',
    'ak': 'AK Interactive',
    'gunze': 'Aqueous Hobby color',
    'federal_standard': 'Federal Standard',
    'tamiya': 'Tamiya',
    'mr_hobby': 'Mr. Color',
    'ral': 'RAL',
    'rlm': 'RLM',
    'humbrol': 'Humbrol',
    'vallejo': 'Vallejo',
    "model_air": 'Vallejo Model Air',
    "model_color": 'Vallejo Model Color',
};

const EQUIVALENT_BRAND_MAP = {
    'HOBBY COLOR': 'Aqueous Hobby color ',
    'MR.COLOR': 'Mr.Color ',
    'TAMIYA': 'Tamiya',
    'RAL': 'RAL',
    'FEDERAL STANDARD': 'Federal Standard',
    'FS': 'Federal Standard',
    'MODEL AIR': 'Vallejo Model Air',
    'MODEL COLOR': 'Vallejo Model Color',
    'AK INTERACTIVE': 'AK Interactive',
    'GUNZE SANGYO': 'Aqueous Hobby color ',
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

    // Check if color itself is in stack
    const colorInStack = !!inStackMap[id];

    // Check if any equivalent of this color is in the stack
    let equivalentInStack = false;
    const primaryEquivalents = Array.isArray(color.equivalents) ? color.equivalents : [];
    for (const eq of primaryEquivalents) {
        const eqBrandId = normalizeBrandId(eq.brand);
        const eqCode = normalizeEquivalentCode(eq.code);
        if (isColorInStack(eqBrandId, eqCode)) {
            equivalentInStack = true;
            break;
        }
    }

    // Also check reverse equivalents (colors from other brands that reference this color)
    if (!equivalentInStack) {
        const secondaryEquivalents = reverseEquivalentIndex.get(getColorKey(brand, color.code)) || [];
        for (const eq of secondaryEquivalents) {
            const eqBrandId = normalizeBrandId(eq.brand);
            const eqCode = normalizeEquivalentCode(eq.code);
            if (isColorInStack(eqBrandId, eqCode)) {
                equivalentInStack = true;
                break;
            }
        }
    }

    // Highlight if color OR any of its equivalents are in stack
    const checked = colorInStack || equivalentInStack;

    const div = document.createElement('div');
    // Add highlight background when color or its equivalents are in stack
    const bgClass = checked ? 'bg-yellow-100 dark:bg-yellow-900' : 'bg-white dark:bg-gray-800';
    div.className = `${bgClass} p-0 rounded-xl shadow-sm flex justify-between text-xl overflow-hidden`;
    div.innerHTML = `
        <div class="w-12 shadow-sm flex-shrink-0" style="background-color: ${hex}; box-shadow: 0 2px 6px rgba(0,0,0,0.12)"></div>
        <div class="flex items-center gap-2 flex-1 p-2 justify-start">
            <div class="flex-1 min-w-0">
                <div class="font-semibold text-xl truncate mb-0">${escapeHtml(color.code)}</div>
                <div class="font-semibold text-xs truncate mb-2">${escapeHtml(color.name || '')}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400"></div>
                <div class="equivalents text-xs text-gray-500 dark:text-gray-400${showEquivalents ? '' : ' hidden'}"></div>
                <div class="secondary-equivalents text-xs text-gray-500 dark:text-gray-400${showEquivalents ? '' : ' hidden'}"></div>
                <button class="stack-btn px-2 py-0.5 rounded border text-xs whitespace-nowrap ${colorInStack ? 'bg-yellow-100 dark:bg-yellow-800 border-yellow-300 dark:border-yellow-600' : 'border-gray-300 dark:border-gray-600'}">${colorInStack ? '✓ Remove' : 'Add'}</button>
            </div>
        </div>
    `;

    const btn = div.querySelector('.stack-btn');
    btn.dataset.colorId = id;
    btn.addEventListener('click', () => toggleColorInStack(brand, id, btn, inStackMap));

    const primaryEqEl = div.querySelector('.equivalents');
    const secondaryEqEl = div.querySelector('.secondary-equivalents');
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
    // Get the main card container (has rounded-xl shadow-sm bg-white/dark:bg-gray-800)
    const mainCard = btn.closest('.rounded-xl.shadow-sm');

    if (inStackMap[id]) {
        delete inStackMap[id];
        btn.textContent = 'Add';
        btn.classList.remove('bg-yellow-100', 'dark:bg-yellow-800', 'border-yellow-300', 'dark:border-yellow-600');
        btn.classList.add('border-gray-300', 'dark:border-gray-600');
        // Remove highlight from card
        if (mainCard) {
            mainCard.classList.remove('bg-yellow-100', 'dark:bg-yellow-900');
            mainCard.classList.add('bg-white', 'dark:bg-gray-800');
        }
    } else {
        inStackMap[id] = true;
        btn.textContent = '✓ Remove';
        btn.classList.remove('border-gray-300', 'dark:border-gray-600');
        btn.classList.add('bg-yellow-100', 'dark:bg-yellow-800', 'border-yellow-300', 'dark:border-yellow-600');
        // Add highlight to card
        if (mainCard) {
            mainCard.classList.remove('bg-white', 'dark:bg-gray-800');
            mainCard.classList.add('bg-yellow-100', 'dark:bg-yellow-900');
        }
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

    // Also update card backgrounds for colors with equivalents in stash
    updateCardHighlights();
}

/**
 * Update card background highlights based on current stash state
 */
function updateCardHighlights() {
    const cards = document.querySelectorAll('.rounded-xl.shadow-sm');
    cards.forEach(card => {
        const btn = card.querySelector('.stack-btn');
        if (!btn || !btn.dataset.colorId) return;

        const [brand, code] = btn.dataset.colorId.split(':');

        // Check if this card's color is in stack
        const colorInStack = isColorInStack(brand, code);

        // Check if any equivalent is in stack (need to get card data from lookup)
        const cardColor = colorLookup.get(btn.dataset.colorId);
        let equivalentInStack = false;
        if (cardColor) {
            // Get all colors in the current list that match this one
            // For now, we need to check the displayed equivalents
            const eqBadges = card.querySelectorAll('[data-eq-brand][data-eq-code]');
            for (const badge of eqBadges) {
                const eqBrand = badge.dataset.eqBrand;
                const eqCode = badge.dataset.eqCode;
                if (isColorInStack(eqBrand, eqCode)) {
                    equivalentInStack = true;
                    break;
                }
            }
        }

        const shouldHighlight = colorInStack || equivalentInStack;
        if (shouldHighlight) {
            card.classList.remove('bg-white', 'dark:bg-gray-800');
            card.classList.add('bg-yellow-100', 'dark:bg-yellow-900');
        } else {
            card.classList.remove('bg-yellow-100', 'dark:bg-yellow-900');
            card.classList.add('bg-white', 'dark:bg-gray-800');
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
    const badgeColor = BRAND_BADGE_COLORS[displayName] || '#6b7280';

    const label = item.code;
    const eqBrandId = normalizeBrandId(item.brand);
    const eqCode = normalizeEquivalentCode(item.code);

    // Check if this equivalent is in the stack
    const inStack = isColorInStack(eqBrandId, eqCode);
    const badgeClass = inStack ? 'ring-2 ring-offset-1 ring-yellow-300 dark:ring-yellow-500' : '';
    const checkIcon = inStack ? ' ✓' : '';

    return `<div class="m-1 rounded px-2 py-0.5 text-xs font-medium text-white cursor-default ${badgeClass}" style="background-color: ${badgeColor}" title="${displayName}${inStack ? ' (in stack)' : ''}" data-eq-brand="${eqBrandId}" data-eq-code="${eqCode}">${label}${checkIcon}</div>`;
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
                            brand: sourceBrand,
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
        const btn = document.createElement('div');

        btn.dataset.brand = b.id;
        btn.className = 'flex flex-col cursor-pointer overflow-hidden rounded border text-xs bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100  items-stretch gap-1 w-20';

        // Add logo
        const logo = document.createElement('img');
        // Use mapped logo filename if available, otherwise use brand ID
        const logoFile = BRAND_LOGO_FILES[b.id] || b.id;
        // Try PNG first, then SVG as fallback
        logo.src = `./logos/${logoFile}.png`;
        logo.alt = b.label;
        logo.className = 'w-full p-1 h-10 rounded object-contain m-2 self-center';
        logo.onerror = () => {
            // Fallback to SVG if PNG not found
            if (logo.src.endsWith('.png')) {
                logo.src = `./logos/${b.id}.svg`;
            } else {
                logo.style.display = 'none'; // Hide if neither PNG nor SVG found
            }
        };
        btn.appendChild(logo);

        // Add label with brand color background
        const label = document.createElement('span');
        label.textContent = b.label;
        label.className = 'text-center flex-1 leading-tight py-1  text-white text-xs font-semibold';
        const brandColor = BRAND_LOGO_COLORS[b.id] || '#666666';
        label.style.backgroundColor = brandColor;
        btn.appendChild(label);

        btn.addEventListener('click', () => {
            // deactivate others
            [...brandTabs.children].forEach(ch => {
                ch.classList.remove('ring-2', 'ring-offset-2');
            });
            // activate this one
            btn.classList.add('ring-2', 'ring-offset-2');
            loadAndRender(b.id);
        });
        brandTabs.appendChild(btn);

        // select first by default
        if (idx === 0 && b.id !== 'my-stack') {
            btn.classList.add('ring-2', 'ring-offset-2');
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
        hideEquivalents();
        return;
    }

    listEl.className = 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 shadow-sm';
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

        colors.forEach(c => {
            const row = renderRow(brand, c, inStack, displayBrand, reverseEquivalentIndex);
            listEl.appendChild(row);
        });


    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-red-500 dark:text-red-400">Unable to load data.</div>';
    }
}




function renderTableView(colors, brand, inStack, reverseEquivalentIndex) {
    // Table view removed - all colors now rendered in card view
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

async function loadStackFromFile(file) {
    // Ensure all packs are loaded before searching for colors
    await Promise.all(BRANDS.map(b => loadPack(b.id).catch(() => null)));

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
                const normalizedInputCode = normalizeEquivalentCode(code);
                for (const [bId, color] of colorLookup) {
                    if (normalizeEquivalentCode(color.code) === normalizedInputCode) {
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

    listEl.className = '';  // Clear grid styling
    listEl.innerHTML = '';

    // Create wrapper for stack items
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full';

    // Action buttons at top
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'flex gap-2 mb-4';

    // Only show "Save to file" if stack has items
    if (items.length > 0) {
        const saveBtn = document.createElement('button');
        saveBtn.id = 'btnSaveStack';
        saveBtn.textContent = 'Save to file';
        saveBtn.className = 'px-3 py-1.5 rounded border text-xs bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-100 dark:hover:bg-gray-600';
        saveBtn.addEventListener('click', saveStackToFile);
        buttonContainer.appendChild(saveBtn);
    }

    // Always show "Load from file"
    const loadLabel = document.createElement('label');
    loadLabel.className = 'px-3 py-1.5 rounded border text-xs bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer';
    loadLabel.textContent = 'Load from file';
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.id = 'stackFileInput';
    fileInput.accept = '.txt';
    fileInput.className = 'hidden';
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (file) {
            await loadStackFromFile(file);
            e.target.value = '';
        }
    });
    loadLabel.appendChild(fileInput);
    buttonContainer.appendChild(loadLabel);

    wrapper.appendChild(buttonContainer);

    if (!items.length) {
        listEl.className = 'flex flex-col items-center justify-center min-h-96';
        const emptyDiv = document.createElement('div');
        emptyDiv.className = 'text-center';
        emptyDiv.innerHTML = `
            <div class="text-2xl font-bold text-gray-400 dark:text-gray-500 mb-4">Your Stack is Empty</div>
            <p class="text-gray-500 dark:text-gray-400 mb-6">Add colors to your stack using the <strong>Add</strong> button on color cards.</p>
        `;
        listEl.appendChild(wrapper);
        listEl.appendChild(emptyDiv);
        return;
    }

    // Grid container for stack items (card view)
    const gridContainer = document.createElement('div');
    gridContainer.className = 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4';

    items.forEach(({ brandId, code }) => {
        const key = `${brandId}:${normalizeEquivalentCode(code)}`;
        const color = colorLookup.get(key);
        const inStack = loadInStack(brandId);

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

        const card = document.createElement('div');
        card.className = 'bg-white dark:bg-gray-700 rounded-xl shadow overflow-hidden flex';
        card.innerHTML = `
            <div class="w-10 flex-shrink-0" style="background-color:${hex}"></div>
            <div class="p-2 min-w-0 flex-1">
                <div class="font-semibold text-sm truncate">${code}</div>
                <div class="text-xs text-gray-500 dark:text-gray-300 truncate leading-tight">${name}</div>
                <div class="mt-1"><span class="text-[10px] px-1 py-0.5 rounded bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-gray-100">${brandLabel}</span></div>
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
    // All Colors modal removed
}

document.addEventListener('DOMContentLoaded', () => {
    createTabs();
    setupTooltip();


    document.getElementById('chkShowEquivalents').addEventListener('change', (e) => {
        showEquivalents = e.target.checked;
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
