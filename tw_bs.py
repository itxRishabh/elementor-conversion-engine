"""tw_bs.py — Tailwind JIT + Bootstrap utility class translators"""
import re

# Full Tailwind color palette (shade 500 defaults)
TW_COLORS = {
    'slate':'64748b','gray':'6b7280','zinc':'71717a','neutral':'737373','stone':'78716c',
    'red':'ef4444','orange':'f97316','amber':'f59e0b','yellow':'eab308','lime':'84cc16',
    'green':'22c55e','emerald':'10b981','teal':'14b8a6','cyan':'06b6d4','sky':'0ea5e9',
    'blue':'3b82f6','indigo':'6366f1','violet':'8b5cf6','purple':'a855f7','fuchsia':'d946ef',
    'pink':'ec4899','rose':'f43f5e','black':'000000','white':'ffffff',
}

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = ''.join(c*2 for c in hex_str)
    try:
        return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
    except ValueError:
        return 0, 0, 0

def is_color_value(val):
    val_lower = val.lower().strip()
    if val_lower.startswith(('#', 'rgb(', 'rgba(', 'hsl(', 'hsla(')):
        return True
    if val_lower in TW_COLORS or val_lower in ['transparent', 'currentcolor', 'inherit', 'initial']:
        return True
    # If it is a string without units, it might be a basic CSS color name (red, blue, etc.)
    if re.match(r'^[a-z]+$', val_lower) and val_lower not in ['auto', 'px', 'full', 'screen']:
        return True
    return False

def resolve_tailwind_color(color_val, opacity=None):
    base_color = color_val.strip()
    if not base_color.startswith('#') and not base_color.startswith(('rgb(', 'rgba(', 'hsl(', 'hsla(')):
        # Check if it is a default tailwind color name
        hex_val = TW_COLORS.get(base_color.lower())
        if hex_val:
            base_color = f"#{hex_val}"

    if opacity is not None:
        op_str = opacity.strip()
        op_val = 1.0
        if op_str.startswith('[') and op_str.endswith(']'):
            try: op_val = float(op_str[1:-1])
            except ValueError: pass
        else:
            try: op_val = int(op_str) / 100.0
            except ValueError: pass

        if base_color.startswith('#'):
            r, g, b = hex_to_rgb(base_color)
            return f"rgba({r}, {g}, {b}, {op_val})"
        elif base_color.startswith('rgb(') and not base_color.startswith('rgba('):
            inner = base_color[4:-1]
            return f"rgba({inner}, {op_val})"
    return base_color

def translate_tailwind_class(cls):
    props = {}
    
    # --- Extract opacity modifier: e.g. bg-red-500/20 or bg-[#ff0000]/[.15] ---
    opacity_val = None
    if '/' in cls:
        parts = cls.split('/', 1)
        cls = parts[0]
        opacity_val = parts[1]

    # --- Arbitrary value: w-[340px], p-[20px], text-[#ff0000], bg-[url(...)] ---
    arb = re.match(r'([a-z-]+)-\[(.+)\]$', cls)
    if arb:
        prefix, val = arb.group(1), arb.group(2)
        arb_map = {
            'w':'width','h':'height','min-w':'min-width','max-w':'max-width',
            'min-h':'min-height','max-h':'max-height','top':'top','left':'left',
            'right':'right','bottom':'bottom','gap':'gap','p':'padding',
            'pt':'padding-top','pr':'padding-right','pb':'padding-bottom','pl':'padding-left',
            'm':'margin','mt':'margin-top','mr':'margin-right','mb':'margin-bottom','ml':'margin-left',
            'tracking':'letter-spacing','leading':'line-height',
            'rounded':'border-radius','opacity':'opacity','z':'z-index',
        }
        
        # Check border-[...]
        if prefix == 'border':
            if is_color_value(val):
                props['border-color'] = resolve_tailwind_color(val, opacity=opacity_val)
            else:
                props['border-width'] = val
        # Check bg-[...]
        elif prefix == 'bg':
            if val.startswith('url'):
                props['background-image'] = val
            else:
                props['background-color'] = resolve_tailwind_color(val, opacity=opacity_val)
        # Check text-[...]
        elif prefix == 'text':
            if is_color_value(val):
                props['color'] = resolve_tailwind_color(val, opacity=opacity_val)
            else:
                props['font-size'] = val
        # Check other property mappings
        elif prefix in arb_map:
            props[arb_map[prefix]] = val
        return props

    # --- Spacing: p-4, pt-2, mx-auto, -mt-4 ---
    sp = re.match(r'(-)?([pm])([tbrlxyse])?-(\d+(?:\.\d+)?|auto|px)$', cls)
    if sp:
        neg, pm, side, size = sp.group(1), sp.group(2), sp.group(3), sp.group(4)
        base = 'padding' if pm == 'p' else 'margin'
        val = 'auto' if size == 'auto' else ('1px' if size == 'px' else f"{float(size)*4}px")
        if neg and val != 'auto': val = f"-{val}"
        sides = {'t':[f'{base}-top'],'b':[f'{base}-bottom'],'r':[f'{base}-right'],'l':[f'{base}-left'],
                 's':[f'{base}-left'],'e':[f'{base}-right'],
                 'x':[f'{base}-left',f'{base}-right'],'y':[f'{base}-top',f'{base}-bottom']}
        for p in (sides.get(side) or [base]): props[p] = val
        return props

    # --- Display ---
    disp = {'flex':'flex','inline-flex':'inline-flex','block':'block','inline-block':'inline-block',
            'inline':'inline','grid':'grid','hidden':'none','table':'table'}
    if cls in disp: props['display'] = disp[cls]; return props

    # --- Flex ---
    flex_map = {'flex-row':('flex-direction','row'),'flex-row-reverse':('flex-direction','row-reverse'),
                'flex-col':('flex-direction','column'),'flex-col-reverse':('flex-direction','column-reverse'),
                'flex-wrap':('flex-wrap','wrap'),'flex-nowrap':('flex-wrap','nowrap'),'flex-wrap-reverse':('flex-wrap','wrap-reverse'),
                'flex-1':('flex','1 1 0%'),'flex-auto':('flex','1 1 auto'),'flex-initial':('flex','0 1 auto'),'flex-none':('flex','none'),
                'grow':('flex-grow','1'),'grow-0':('flex-grow','0'),'shrink':('flex-shrink','1'),'shrink-0':('flex-shrink','0')}
    if cls in flex_map: props[flex_map[cls][0]] = flex_map[cls][1]; return props

    # --- Align / Justify ---
    aj = {'items-start':('align-items','flex-start'),'items-end':('align-items','flex-end'),'items-center':('align-items','center'),
          'items-baseline':('align-items','baseline'),'items-stretch':('align-items','stretch'),
          'justify-start':('justify-content','flex-start'),'justify-end':('justify-content','flex-end'),
          'justify-center':('justify-content','center'),'justify-between':('justify-content','space-between'),
          'justify-around':('justify-content','space-around'),'justify-evenly':('justify-content','space-evenly'),
          'self-auto':('align-self','auto'),'self-start':('align-self','flex-start'),'self-end':('align-self','flex-end'),
          'self-center':('align-self','center'),'self-stretch':('align-self','stretch'),
          'content-start':('align-content','flex-start'),'content-end':('align-content','flex-end'),
          'content-center':('align-content','center'),'content-between':('align-content','space-between')}
    if cls in aj: props[aj[cls][0]] = aj[cls][1]; return props

    # --- Gap ---
    gm = re.match(r'gap-([xy])?-?(\d+(?:\.\d+)?)$', cls)
    if gm:
        axis, sz = gm.group(1), gm.group(2)
        val = f"{float(sz)*4}px"
        if axis == 'x': props['column-gap'] = val
        elif axis == 'y': props['row-gap'] = val
        else: props['gap'] = val
        return props

    # --- Width / Height ---
    for prop_prefix, css_prop in [('w','width'),('h','height'),('min-w','min-width'),('max-w','max-width'),('min-h','min-height'),('max-h','max-height')]:
        wm = re.match(rf'^{re.escape(prop_prefix)}-(full|screen|min|max|fit|auto|\d+/\d+|\d+(?:\.\d+)?)$', cls)
        if wm:
            v = wm.group(1)
            kw = {'full':'100%','screen':'100vw' if 'w' in prop_prefix else '100vh','min':'min-content','max':'max-content','fit':'fit-content','auto':'auto'}
            if v in kw: props[css_prop] = kw[v]
            elif '/' in v:
                n, d = map(float, v.split('/'))
                props[css_prop] = f"{round(n/d*100,4)}%"
            else: props[css_prop] = f"{float(v)*4}px"
            return props

    # --- Position ---
    pos = {'static':'static','fixed':'fixed','absolute':'absolute','relative':'relative','sticky':'sticky'}
    if cls in pos: props['position'] = pos[cls]; return props

    # --- Inset ---
    for ip, sides in [('inset',['top','right','bottom','left']),('inset-x',['left','right']),('inset-y',['top','bottom'])]:
        im = re.match(rf'^{ip}-(\d+(?:\.\d+)?|auto)$', cls)
        if im:
            v = 'auto' if im.group(1)=='auto' else f"{float(im.group(1))*4}px"
            for s in sides: props[s] = v
            return props
    for d in ['top','right','bottom','left']:
        dm = re.match(rf'^{d}-(\d+(?:\.\d+)?|auto)$', cls)
        if dm:
            props[d] = 'auto' if dm.group(1)=='auto' else f"{float(dm.group(1))*4}px"
            return props

    # --- Z-index ---
    zm = re.match(r'^z-(\d+|auto)$', cls)
    if zm: props['z-index'] = zm.group(1); return props

    # --- Overflow ---
    ov = {'overflow-auto':('overflow','auto'),'overflow-hidden':('overflow','hidden'),'overflow-visible':('overflow','visible'),
          'overflow-scroll':('overflow','scroll'),'overflow-x-auto':('overflow-x','auto'),'overflow-y-auto':('overflow-y','auto'),
          'overflow-x-hidden':('overflow-x','hidden'),'overflow-y-hidden':('overflow-y','hidden')}
    if cls in ov: props[ov[cls][0]] = ov[cls][1]; return props

    # --- Opacity ---
    om = re.match(r'^opacity-(\d+)$', cls)
    if om: props['opacity'] = str(int(om.group(1))/100); return props

    # --- Font size ---
    sz_map = {'xs':'0.75rem','sm':'0.875rem','base':'1rem','lg':'1.125rem','xl':'1.25rem',
              '2xl':'1.5rem','3xl':'1.875rem','4xl':'2.25rem','5xl':'3rem','6xl':'3.75rem','7xl':'4.5rem','8xl':'6rem','9xl':'8rem'}
    tsm = re.match(r'^text-(xs|sm|base|lg|\d?xl)$', cls)
    if tsm and tsm.group(1) in sz_map: props['font-size'] = sz_map[tsm.group(1)]; return props

    # --- Text align ---
    ta = {'text-left':'left','text-center':'center','text-right':'right','text-justify':'justify'}
    if cls in ta: props['text-align'] = ta[cls]; return props

    # --- Font weight ---
    fw = {'font-thin':'100','font-extralight':'200','font-light':'300','font-normal':'400','font-medium':'500',
          'font-semibold':'600','font-bold':'700','font-extrabold':'800','font-black':'900'}
    if cls in fw: props['font-weight'] = fw[cls]; return props

    # --- Font style ---
    if cls == 'italic': props['font-style'] = 'italic'; return props
    if cls == 'not-italic': props['font-style'] = 'normal'; return props

    # --- Text decoration ---
    td = {'underline':'underline','overline':'overline','line-through':'line-through','no-underline':'none'}
    if cls in td: props['text-decoration'] = td[cls]; return props

    # --- Text transform ---
    tt = {'uppercase':'uppercase','lowercase':'lowercase','capitalize':'capitalize','normal-case':'none'}
    if cls in tt: props['text-transform'] = tt[cls]; return props

    # --- Letter spacing ---
    ls = {'tracking-tighter':'-0.05em','tracking-tight':'-0.025em','tracking-normal':'0em',
          'tracking-wide':'0.025em','tracking-wider':'0.05em','tracking-widest':'0.1em'}
    if cls in ls: props['letter-spacing'] = ls[cls]; return props

    # --- Line height ---
    lh = {'leading-none':'1','leading-tight':'1.25','leading-snug':'1.375','leading-normal':'1.5',
          'leading-relaxed':'1.625','leading-loose':'2'}
    if cls in lh: props['line-height'] = lh[cls]; return props
    lhm = re.match(r'^leading-(\d+)$', cls)
    if lhm: props['line-height'] = f"{float(lhm.group(1))*4}px"; return props

    # --- Border radius ---
    br = {'rounded-none':'0','rounded-sm':'0.125rem','rounded':'0.25rem','rounded-md':'0.375rem',
          'rounded-lg':'0.5rem','rounded-xl':'0.75rem','rounded-2xl':'1rem','rounded-3xl':'1.5rem','rounded-full':'9999px'}
    if cls in br: props['border-radius'] = br[cls]; return props

    # --- Box shadow ---
    sh = {'shadow-sm':'0 1px 2px 0 rgba(0,0,0,0.05)','shadow':'0 1px 3px 0 rgba(0,0,0,0.1),0 1px 2px -1px rgba(0,0,0,0.1)',
          'shadow-md':'0 4px 6px -1px rgba(0,0,0,0.1),0 2px 4px -2px rgba(0,0,0,0.1)',
          'shadow-lg':'0 10px 15px -3px rgba(0,0,0,0.1),0 4px 6px -4px rgba(0,0,0,0.1)',
          'shadow-xl':'0 20px 25px -5px rgba(0,0,0,0.1),0 8px 10px -6px rgba(0,0,0,0.1)',
          'shadow-2xl':'0 25px 50px -12px rgba(0,0,0,0.25)','shadow-none':'none'}
    if cls in sh: props['box-shadow'] = sh[cls]; return props

    # --- Aspect ratio ---
    ar = {'aspect-auto':'auto','aspect-square':'1/1','aspect-video':'16/9'}
    if cls in ar: props['aspect-ratio'] = ar[cls]; return props

    # --- Grid ---
    gcm = re.match(r'^grid-cols-(\d+)$', cls)
    if gcm: props['display'] = 'grid'; props['grid-template-columns'] = f"repeat({gcm.group(1)},minmax(0,1fr))"; return props
    grm = re.match(r'^grid-rows-(\d+)$', cls)
    if grm: props['grid-template-rows'] = f"repeat({grm.group(1)},minmax(0,1fr))"; return props
    csm = re.match(r'^col-span-(\d+)$', cls)
    if csm: props['grid-column'] = f"span {csm.group(1)} / span {csm.group(1)}"; return props

    # --- BG color ---
    bgm = re.match(r'^bg-([a-z]+)(?:-(\d+))?$', cls)
    if bgm and bgm.group(1) in TW_COLORS:
        base = f"#{TW_COLORS[bgm.group(1)]}"
        props['background-color'] = resolve_tailwind_color(base, opacity=opacity_val)
        return props
    if cls == 'bg-transparent': props['background-color'] = 'transparent'; return props

    # --- Text color ---
    tcm = re.match(r'^text-([a-z]+)(?:-(\d+))?$', cls)
    if tcm and tcm.group(1) in TW_COLORS:
        base = f"#{TW_COLORS[tcm.group(1)]}"
        props['color'] = resolve_tailwind_color(base, opacity=opacity_val)
        return props

    # --- Border color ---
    bcm = re.match(r'^border-([a-z]+)(?:-(\d+))?$', cls)
    if bcm and bcm.group(1) in TW_COLORS:
        base = f"#{TW_COLORS[bcm.group(1)]}"
        props['border-color'] = resolve_tailwind_color(base, opacity=opacity_val)
        return props

    # --- Border width ---
    bwm = re.match(r'^border(?:-(t|r|b|l|x|y))?(?:-(\d+))?$', cls)
    if bwm:
        w = f"{bwm.group(2) or '1'}px"
        side = bwm.group(1)
        if not side: props['border-width'] = w
        elif side == 't': props['border-top-width'] = w
        elif side == 'r': props['border-right-width'] = w
        elif side == 'b': props['border-bottom-width'] = w
        elif side == 'l': props['border-left-width'] = w
        elif side == 'x': props['border-left-width'] = w; props['border-right-width'] = w
        elif side == 'y': props['border-top-width'] = w; props['border-bottom-width'] = w
        return props

    # --- Cursor ---
    cu = {'cursor-pointer':'pointer','cursor-default':'default','cursor-wait':'wait','cursor-text':'text',
          'cursor-move':'move','cursor-not-allowed':'not-allowed'}
    if cls in cu: props['cursor'] = cu[cls]; return props

    # --- Object fit ---
    of = {'object-contain':'contain','object-cover':'cover','object-fill':'fill','object-none':'none','object-scale-down':'scale-down'}
    if cls in of: props['object-fit'] = of[cls]; return props

    return props


def translate_bootstrap_class(cls):
    props = {}
    bs_sp = {'0':'0px','1':'4px','2':'8px','3':'16px','4':'24px','5':'48px','auto':'auto'}

    # --- Spacing ---
    sp = re.match(r'^([pm])([tbrlxsye])?-(\d|auto)$', cls)
    if sp:
        pm, side, sz = sp.group(1), sp.group(2), sp.group(3)
        base = 'padding' if pm == 'p' else 'margin'
        val = bs_sp.get(sz, '0px')
        sides_map = {'t':[f'{base}-top'],'b':[f'{base}-bottom'],'r':[f'{base}-right'],'e':[f'{base}-right'],
                     'l':[f'{base}-left'],'s':[f'{base}-left'],
                     'x':[f'{base}-left',f'{base}-right'],'y':[f'{base}-top',f'{base}-bottom']}
        for p in (sides_map.get(side) or [base]): props[p] = val
        return props

    # --- Display ---
    dd = {'d-flex':'flex','d-inline-flex':'inline-flex','d-block':'block','d-inline-block':'inline-block',
          'd-inline':'inline','d-grid':'grid','d-none':'none','d-table':'table'}
    if cls in dd: props['display'] = dd[cls]; return props

    # --- Flex ---
    ff = {'flex-row':('flex-direction','row'),'flex-row-reverse':('flex-direction','row-reverse'),
          'flex-column':('flex-direction','column'),'flex-column-reverse':('flex-direction','column-reverse'),
          'flex-wrap':('flex-wrap','wrap'),'flex-nowrap':('flex-wrap','nowrap'),
          'flex-fill':('flex','1 1 auto'),'flex-grow-0':('flex-grow','0'),'flex-grow-1':('flex-grow','1'),
          'flex-shrink-0':('flex-shrink','0'),'flex-shrink-1':('flex-shrink','1')}
    if cls in ff: props[ff[cls][0]] = ff[cls][1]; return props

    # --- Justify / Align ---
    ja = {'justify-content-start':('justify-content','flex-start'),'justify-content-end':('justify-content','flex-end'),
          'justify-content-center':('justify-content','center'),'justify-content-between':('justify-content','space-between'),
          'justify-content-around':('justify-content','space-around'),'justify-content-evenly':('justify-content','space-evenly'),
          'align-items-start':('align-items','flex-start'),'align-items-end':('align-items','flex-end'),
          'align-items-center':('align-items','center'),'align-items-baseline':('align-items','baseline'),
          'align-items-stretch':('align-items','stretch'),'align-self-start':('align-self','flex-start'),
          'align-self-end':('align-self','flex-end'),'align-self-center':('align-self','center'),
          'align-self-stretch':('align-self','stretch')}
    if cls in ja: props[ja[cls][0]] = ja[cls][1]; return props

    # --- Text ---
    tx = {'text-start':'left','text-center':'center','text-end':'right'}
    if cls in tx: props['text-align'] = tx[cls]; return props
    fw = {'fw-bold':'700','fw-bolder':'800','fw-semibold':'600','fw-medium':'500','fw-normal':'400','fw-light':'300','fw-lighter':'200'}
    if cls in fw: props['font-weight'] = fw[cls]; return props
    if cls == 'fst-italic': props['font-style'] = 'italic'; return props
    if cls == 'fst-normal': props['font-style'] = 'normal'; return props
    if cls == 'text-decoration-none': props['text-decoration'] = 'none'; return props
    if cls == 'text-uppercase': props['text-transform'] = 'uppercase'; return props
    if cls == 'text-lowercase': props['text-transform'] = 'lowercase'; return props
    if cls == 'text-capitalize': props['text-transform'] = 'capitalize'; return props

    # --- Position ---
    pp = {'position-static':'static','position-relative':'relative','position-absolute':'absolute',
          'position-fixed':'fixed','position-sticky':'sticky'}
    if cls in pp: props['position'] = pp[cls]; return props

    # --- Border radius ---
    if cls == 'rounded': props['border-radius'] = '0.375rem'
    elif cls == 'rounded-pill': props['border-radius'] = '50rem'
    elif cls == 'rounded-circle': props['border-radius'] = '50%'
    elif cls == 'rounded-0': props['border-radius'] = '0'

    # --- Overflow ---
    if cls == 'overflow-auto': props['overflow'] = 'auto'
    elif cls == 'overflow-hidden': props['overflow'] = 'hidden'
    elif cls == 'overflow-visible': props['overflow'] = 'visible'
    elif cls == 'overflow-scroll': props['overflow'] = 'scroll'

    # --- Shadow ---
    if cls == 'shadow': props['box-shadow'] = '0 .5rem 1rem rgba(0,0,0,.15)'
    elif cls == 'shadow-sm': props['box-shadow'] = '0 .125rem .25rem rgba(0,0,0,.075)'
    elif cls == 'shadow-lg': props['box-shadow'] = '0 1rem 3rem rgba(0,0,0,.175)'
    elif cls == 'shadow-none': props['box-shadow'] = 'none'

    # --- Gap (BS5) ---
    gm = re.match(r'^gap-(\d)$', cls)
    if gm: props['gap'] = bs_sp.get(gm.group(1), '0px')

    # --- Width ---
    wm = re.match(r'^w-(\d+)$', cls)
    if wm and int(wm.group(1)) in [25,50,75,100]: props['width'] = f"{wm.group(1)}%"

    return props
