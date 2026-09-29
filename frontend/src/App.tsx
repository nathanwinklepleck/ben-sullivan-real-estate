import { useEffect, useEffectEvent, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import sampleDeal from '../../sample_deal.json'
import './App.css'

type UnitMixRow = { unit_type: string; count: number; average_sf: number; current_rent_monthly: number; stabilized_rent_monthly: number }
type TenantRow = { name: string; suite?: string; area_sf: number; lease_start: string; lease_end: string; current_rent: number; vacant?: boolean; lease_up_date?: string | null; extension_end?: string | null; renewal_ti_per_sf?: number; new_lease_ti_per_sf?: number; renewal_commission_rate?: number; new_lease_commission_rate?: number; rent_basis: 'per_sf_year' | 'per_month'; lease_structure: 'gross' | 'modified_gross' | 'nn' | 'nnn'; recoverable_expenses: string[]; expense_stop_per_sf: number; renewal_probability: number; downtime_months: number; market_rent_per_sf: number; new_lease_term_months: number; renewal_rent_per_sf: number | null; rent_steps: Array<{ effective_date: string; rent: number }> }
type RentRollPreview = { rows: TenantRow[]; warnings: string[]; total_area_sf: number; occupied_area_sf: number; annual_base_rent: number }
type Loan = { name: string; amount: number; rate: number; rate_type: 'fixed' | 'floating'; spread: number; interest_only_months: number; amortization_years: number; term_months: number; origination_fee_rate: number }
type WaterfallTier = { name: string; hurdle_irr: number | null; lp_split: number; gp_split: number }
type Investor = { gp_coinvest_pct: number; minimum_investment: number; preferred_return_rate: number; gp_catch_up: boolean; tiers: WaterfallTier[] }
type Deal = Omit<typeof sampleDeal, 'unit_mix' | 'rent_roll' | 'loans' | 'investor' | 'property_type' | 'deal_type' | 'uses' | 'sources' | 'expenses'> & { property_type: 'multifamily' | 'retail' | 'office' | 'industrial'; deal_type: 'acquisition' | 'development'; unit_mix: UnitMixRow[]; rent_roll: TenantRow[]; loans: Loan[]; investor: Investor; uses: Record<string, number>; sources: Record<string, number>; expenses: Record<string, number> }
type WaterfallResults = { lp_irr: number | null; gp_irr: number | null; lp_equity_multiple: number; gp_equity_multiple: number; lp_contributions: number; gp_contributions: number; lp_distributions: number; gp_distributions: number }
type Results = { total_uses: number; total_debt: number; required_equity: number; unlevered_irr: number | null; levered_irr: number | null; levered_equity_multiple: number; average_cash_on_cash: number; stabilized_yield_on_cost: number; exit_value: number; annual_cash_flows: Array<{ year: number; net_operating_income: number; levered_cash_flow: number }>; exit_cap_sensitivity: Array<{ exit_cap_rate: number | null; levered_irr: number | null; equity_multiple: number }>; hold_period_sensitivity: Array<{ hold_years: number | null; levered_irr: number | null; equity_multiple: number }>; waterfall: WaterfallResults | null }
type SavedDeal = { id: string; property_name: string }
type ImageSlot = 'cover' | 'sponsor' | 'market' | 'location' | 'site' | 'property_exterior' | 'property_living_room' | 'property_kitchen' | 'property_amenity' | 'track_record_exterior' | 'track_record_context'
type DealImage = { id: string; slot: ImageSlot; original_name: string; content_type: string; caption: string }

const imageSlots: Array<{ slot: ImageSlot; label: string }> = [
  { slot: 'cover', label: 'Cover image' }, { slot: 'sponsor', label: 'Sponsor portrait' },
  { slot: 'market', label: 'Market context' }, { slot: 'location', label: 'Location overview' },
  { slot: 'site', label: 'Site / unit overview' }, { slot: 'property_exterior', label: 'Property exterior' },
  { slot: 'property_living_room', label: 'Living room / interior' }, { slot: 'property_kitchen', label: 'Kitchen / finishes' },
  { slot: 'property_amenity', label: 'Amenities / common area' }, { slot: 'track_record_exterior', label: 'Track record asset' },
  { slot: 'track_record_context', label: 'Track record context' },
]

const holds = [5, 6, 7, 8, 9, 10]
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
const percent = (value: number | null) => value === null ? 'N/M' : `${(value * 100).toFixed(1)}%`

function App() {
  const [deal, setDeal] = useState<Deal>(() => JSON.parse(JSON.stringify(sampleDeal)) as Deal)
  const [results, setResults] = useState<Results | null>(null)
  const [savedDeals, setSavedDeals] = useState<SavedDeal[]>([])
  const [images, setImages] = useState<DealImage[]>([])
  const [dealId, setDealId] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  const calculateInitial = useEffectEvent(() => calculate(deal))

  useEffect(() => {
    void calculateInitial()
    void refreshSavedDeals()
  }, [])

  async function calculate(current: Deal) {
    setBusy(true)
    try {
      const response = await fetch('/api/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(current) })
      if (!response.ok) throw new Error(await errorMessage(response))
      setResults((await response.json()) as Results)
      setNotice('Model updated')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Calculation failed')
    } finally { setBusy(false) }
  }

  async function refreshSavedDeals() {
    try {
      const response = await fetch('/api/deals')
      if (response.ok) setSavedDeals((await response.json()) as SavedDeal[])
    } catch { setSavedDeals([]) }
  }

  async function refreshImages(id: string) {
    try {
      const response = await fetch(`/api/deals/${id}/images`)
      if (response.ok) setImages((await response.json()) as DealImage[])
    } catch { setImages([]) }
  }

  function update<K extends keyof Deal>(key: K, value: Deal[K]) {
    setDeal((current) => {
      if (key === 'property_type' && value !== 'multifamily' && current.rent_roll.length === 0) {
        return { ...current, [key]: value, rent_roll: [newTenant(current)] }
      }
      return { ...current, [key]: value }
    })
  }

  function updateNested(group: 'uses' | 'sources' | 'expenses', key: string, value: number) {
    setDeal((current) => ({ ...current, [group]: { ...current[group], [key]: value } }))
  }

  function updateInvestor<K extends keyof Investor>(key: K, value: Investor[K]) {
    setDeal((current) => ({ ...current, investor: { ...current.investor, [key]: value } }))
  }

  function updateTier<K extends keyof WaterfallTier>(index: number, key: K, value: WaterfallTier[K]) {
    setDeal((current) => ({ ...current, investor: { ...current.investor, tiers: current.investor.tiers.map((tier, tierIndex) => tierIndex === index ? { ...tier, [key]: value } : tier) } }))
  }

  function updateLoan<K extends keyof Loan>(index: number, key: K, value: Loan[K]) {
    setDeal((current) => ({ ...current, loans: current.loans.map((loan, loanIndex) => loanIndex === index ? { ...loan, [key]: value } : loan) }))
  }

  async function saveDeal(): Promise<string | null> {
    setBusy(true)
    try {
      const response = await fetch(dealId ? `/api/deals/${dealId}` : '/api/deals', { method: dealId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(deal) })
      if (!response.ok) throw new Error(await errorMessage(response))
      const saved = (await response.json()) as { id: string }
      setDealId(saved.id)
      await refreshSavedDeals()
      setNotice('Deal saved')
      return saved.id
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not save deal'); return null }
    finally { setBusy(false) }
  }

  async function loadDeal(id: string) {
    if (!id) return
    setBusy(true)
    try {
      const response = await fetch(`/api/deals/${id}`)
      if (!response.ok) throw new Error(await errorMessage(response))
      const loaded = (await response.json()) as Deal
      setDeal(loaded)
      setDealId(id)
      await refreshImages(id)
      void calculate(loaded)
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not load deal') }
    finally { setBusy(false) }
  }

  async function uploadImage(slot: ImageSlot, file: File) {
    setBusy(true)
    try {
      const id = dealId || await saveDeal()
      if (!id) return
      const form = new FormData()
      form.append('slot', slot)
      form.append('file', file)
      const response = await fetch(`/api/deals/${id}/images`, { method: 'POST', body: form })
      if (!response.ok) throw new Error(await errorMessage(response))
      const uploaded = (await response.json()) as DealImage
      setImages((current) => [...current.filter((image) => image.slot !== slot), uploaded])
      setNotice(`${file.name} uploaded`)
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not upload image') }
    finally { setBusy(false) }
  }

  async function deleteImage(image: DealImage) {
    if (!dealId) return
    setBusy(true)
    try {
      const response = await fetch(`/api/deals/${dealId}/images/${image.id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error(await errorMessage(response))
      setImages((current) => current.filter((item) => item.id !== image.id))
      setNotice(`${image.original_name} removed`)
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not remove image') }
    finally { setBusy(false) }
  }

  async function downloadOm() {
    setBusy(true)
    try {
      const reportUrl = dealId ? `/api/report?deal_id=${encodeURIComponent(dealId)}` : '/api/report'
      const response = await fetch(reportUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(deal) })
      if (!response.ok) throw new Error(await errorMessage(response))
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `${deal.property_name.toLowerCase().replaceAll(' ', '-')}-om.pdf`
      link.click()
      URL.revokeObjectURL(url)
      setNotice('Offering memorandum downloaded')
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not create PDF') }
    finally { setBusy(false) }
  }

  const unitCount = deal.property_type === 'multifamily' ? deal.unit_mix.reduce((total, row) => total + row.count, 0) : 0
  const area = deal.total_nra_sf || deal.unit_mix.reduce((total, row) => total + row.count * row.average_sf, 0)
  const usesTotal = Object.values(deal.uses).reduce((total, value) => total + value, 0)

  return <div className="app-shell">
    <header className="topbar"><a className="wordmark" href="#top"><span className="wordmark-mark">K</span><span>KINGDOM REALTY</span></a><div className="topbar-center">UNDERWRITING DESK <span>/</span> DEVELOPMENT &amp; ACQUISITION</div><div className="topbar-actions"><select aria-label="Load saved deal" value={dealId} onChange={(event) => void loadDeal(event.target.value)}><option value="">Saved deals</option>{savedDeals.map((saved) => <option key={saved.id} value={saved.id}>{saved.property_name}</option>)}</select><button type="button" onClick={() => void saveDeal()} disabled={busy}>Save deal</button><button className="primary-button" type="button" onClick={() => void downloadOm()} disabled={busy}>Export OM</button></div></header>
    <main id="top" className="workspace">
      <section className="intro-row"><div><p className="eyebrow">Investment analysis | {deal.deal_type === 'development' ? 'Ground-up development' : 'Acquisition'}</p><h1>{deal.property_name}</h1><p className="subhead">{deal.address} | {deal.property_type} | {deal.property_type === 'multifamily' ? `${unitCount} residences` : `${deal.rent_roll.length} suites`} | {deal.hold_years}-year hold</p></div><span className="notice" role="status">{busy ? 'Working...' : notice}</span></section>
      <div className="work-grid"><form onSubmit={(event) => { event.preventDefault(); void calculate(deal) }}>
        <details className="form-section" open><summary><b>01</b> Deal &amp; property <small>Identity | basis | hold period</small></summary><div className="fields three-cols">
          <Field label="Property name" value={deal.property_name} onChange={(value) => update('property_name', value)} /><Field label="Property type" value={deal.property_type} select options={['multifamily', 'retail', 'office', 'industrial']} onChange={(value) => update('property_type', value as Deal['property_type'])} /><Field label="Business plan" value={deal.deal_type} select options={['acquisition', 'development']} onChange={(value) => update('deal_type', value as Deal['deal_type'])} /><Field label="Property address" value={deal.address} onChange={(value) => update('address', value)} /><Field label="Units" value={deal.units} type="number" onChange={(value) => update('units', Number(value))} /><Field label="Rentable area" value={deal.total_nra_sf} type="number" suffix="SF" onChange={(value) => update('total_nra_sf', Number(value))} /><Field label="Closing / start date" value={deal.closing_date} type="date" onChange={(value) => update('closing_date', value)} /><Field label="Analysis start date" value={deal.analysis_start_date} type="date" onChange={(value) => update('analysis_start_date', value)} /><Field label="Hold period" value={deal.hold_years} select options={holds.map(String)} suffix="years" onChange={(value) => update('hold_years', Number(value))} />
        </div></details>

        <details className="form-section" open><summary><b>02</b> Sources &amp; uses <small>Cost basis | capital stack</small></summary><div className="form-columns"><div><h3>Project uses</h3>{Object.entries(deal.uses).map(([key, value]) => <Field key={key} label={key.replaceAll('_', ' ')} value={value} type="number" prefix="$" onChange={(next) => updateNested('uses', key, Number(next))} />)}</div><div><h3>Non-debt sources</h3>{Object.entries(deal.sources).map(([key, value]) => <Field key={key} label={key.replaceAll('_', ' ')} value={value} type="number" prefix="$" onChange={(next) => updateNested('sources', key, Number(next))} />)}<p className="basis-line">Cost / unit <strong>{money(usesTotal / Math.max(unitCount, 1))}</strong></p><p className="basis-line">Cost / SF <strong>{money(usesTotal / Math.max(area, 1))}</strong></p><p className="basis-line">Total uses <strong>{money(usesTotal)}</strong></p></div></div></details>

        <details className="form-section"><summary><b>03</b> Debt <small>Up to three loan tranches</small></summary><div className="section-body">{deal.loans.map((loan, index) => <div className="fields three-cols loan" key={`${loan.name}-${index}`}><h3>{loan.name}</h3><Field label="Loan amount" value={loan.amount} type="number" prefix="$" onChange={(value) => updateLoan(index, 'amount', Number(value))} /><Field label="Interest rate" value={loan.rate * 100} type="number" suffix="%" onChange={(value) => updateLoan(index, 'rate', Number(value) / 100)} /><Field label="Rate type" value={loan.rate_type} select options={['fixed', 'floating']} onChange={(value) => updateLoan(index, 'rate_type', value as Loan['rate_type'])} /><Field label="Spread" value={loan.spread * 100} type="number" suffix="%" onChange={(value) => updateLoan(index, 'spread', Number(value) / 100)} /><Field label="Interest-only period" value={loan.interest_only_months} type="number" suffix="months" onChange={(value) => updateLoan(index, 'interest_only_months', Number(value))} /><Field label="Amortization" value={loan.amortization_years} type="number" suffix="years" onChange={(value) => updateLoan(index, 'amortization_years', Number(value))} /><Field label="Term / maturity" value={loan.term_months} type="number" suffix="months" onChange={(value) => updateLoan(index, 'term_months', Number(value))} /><Field label="Origination fee" value={loan.origination_fee_rate * 100} type="number" suffix="%" onChange={(value) => updateLoan(index, 'origination_fee_rate', Number(value) / 100)} /></div>)}<button className="text-button" type="button" disabled={deal.loans.length >= 3} onClick={() => setDeal((current) => ({ ...current, loans: [...current.loans, { name: `Loan ${current.loans.length + 1}`, amount: 0, rate: 0.07, rate_type: 'fixed', spread: 0, interest_only_months: 0, amortization_years: 25, term_months: current.hold_years * 12, origination_fee_rate: 0 }] }))}>+ Add tranche</button></div></details>

        <details className="form-section"><summary><b>04</b> Operating assumptions <small>Revenue | expenses | lease-up</small></summary><div className="section-body fields three-cols">
          <Field label="Vacancy / collection loss" value={deal.vacancy_rate * 100} type="number" suffix="%" onChange={(value) => update('vacancy_rate', Number(value) / 100)} /><Field label="Concessions" value={deal.concessions_rate * 100} type="number" suffix="%" onChange={(value) => update('concessions_rate', Number(value) / 100)} /><Field label="Bad debt" value={deal.bad_debt_rate * 100} type="number" suffix="%" onChange={(value) => update('bad_debt_rate', Number(value) / 100)} /><Field label="Other income / unit / month" value={deal.other_income_per_unit_monthly} type="number" prefix="$" onChange={(value) => update('other_income_per_unit_monthly', Number(value))} /><Field label="Revenue escalation" value={deal.revenue_growth_rate * 100} type="number" suffix="%" onChange={(value) => update('revenue_growth_rate', Number(value) / 100)} /><Field label="Expense escalation" value={deal.expense_growth_rate * 100} type="number" suffix="%" onChange={(value) => update('expense_growth_rate', Number(value) / 100)} /><Field label="Reserve / unit / year" value={deal.replacement_reserve_per_unit_annual} type="number" prefix="$" onChange={(value) => update('replacement_reserve_per_unit_annual', Number(value))} />{Object.entries(deal.expenses).map(([key, value]) => <Field key={key} label={key.replaceAll('_', ' ')} value={key === 'management_rate' ? value * 100 : value} type="number" prefix={key === 'management_rate' ? undefined : '$'} suffix={key === 'management_rate' ? '%' : undefined} onChange={(next) => updateNested('expenses', key, Number(next) / (key === 'management_rate' ? 100 : 1))} />)}<Field label="Construction period" value={deal.construction_months} type="number" suffix="months" onChange={(value) => update('construction_months', Number(value))} /><Field label="Lease-up absorption" value={deal.lease_up_absorption_units_monthly} type="number" suffix="units / month" onChange={(value) => update('lease_up_absorption_units_monthly', Number(value))} /><Field label="Stabilization month" value={deal.stabilization_month} type="number" suffix="month" onChange={(value) => update('stabilization_month', Number(value))} />
        </div></details>

        <details className="form-section" open><summary><b>05</b> {deal.property_type === 'multifamily' ? 'Unit mix' : 'Tenant rent roll'} <small>{deal.property_type === 'multifamily' ? `${deal.unit_mix.length} unit types` : `${deal.rent_roll.length} of 500 suites`}</small></summary><div className="section-body">{deal.property_type === 'multifamily' ? <><div className="unit-table unit-head"><span>Unit type</span><span>Count</span><span>Avg SF</span><span>Current rent</span><span>Stabilized rent</span></div>{deal.unit_mix.map((row, index) => <div className="unit-table" key={`${row.unit_type}-${index}`}><input aria-label="Unit type" value={row.unit_type} onChange={(event) => changeUnit(setDeal, index, 'unit_type', event.target.value)} /><input aria-label="Count" type="number" value={row.count} onChange={(event) => changeUnit(setDeal, index, 'count', Number(event.target.value))} /><input aria-label="Average SF" type="number" value={row.average_sf} onChange={(event) => changeUnit(setDeal, index, 'average_sf', Number(event.target.value))} /><input aria-label="Current rent" type="number" value={row.current_rent_monthly} onChange={(event) => changeUnit(setDeal, index, 'current_rent_monthly', Number(event.target.value))} /><input aria-label="Stabilized rent" type="number" value={row.stabilized_rent_monthly} onChange={(event) => changeUnit(setDeal, index, 'stabilized_rent_monthly', Number(event.target.value))} /></div>)}</> : <>{deal.rent_roll.map((tenant, index) => <div className="fields three-cols tenant" key={`${tenant.name}-${index}`}><Field label="Tenant / suite" value={tenant.name} onChange={(value) => changeTenant(setDeal, index, 'name', value)} /><Field label="Area" value={tenant.area_sf} type="number" suffix="SF" onChange={(value) => changeTenant(setDeal, index, 'area_sf', Number(value))} /><Field label="Structure" value={tenant.lease_structure} select options={['gross', 'modified_gross', 'nn', 'nnn']} onChange={(value) => changeTenant(setDeal, index, 'lease_structure', value as TenantRow['lease_structure'])} /><Field label="Lease start" value={tenant.lease_start} type="date" onChange={(value) => changeTenant(setDeal, index, 'lease_start', value)} /><Field label="Lease end" value={tenant.lease_end} type="date" onChange={(value) => changeTenant(setDeal, index, 'lease_end', value)} /><Field label="Current rent" value={tenant.current_rent} type="number" prefix="$" onChange={(value) => changeTenant(setDeal, index, 'current_rent', Number(value))} /><Field label="Market rent / SF" value={tenant.market_rent_per_sf} type="number" prefix="$" onChange={(value) => changeTenant(setDeal, index, 'market_rent_per_sf', Number(value))} /><Field label="Renewal probability" value={tenant.renewal_probability * 100} type="number" suffix="%" onChange={(value) => changeTenant(setDeal, index, 'renewal_probability', Number(value) / 100)} /><Field label="Downtime" value={tenant.downtime_months} type="number" suffix="months" onChange={(value) => changeTenant(setDeal, index, 'downtime_months', Number(value))} /></div>)}</>}</div></details>

        {deal.property_type === 'multifamily' ? <button className="text-button" type="button" onClick={() => setDeal((current) => { const source = current.unit_mix[0]; return source ? { ...current, units: current.units + 1, unit_mix: [...current.unit_mix, { ...source, unit_type: 'Additional type', count: 1 }] } : current })}>+ Add unit type</button> : <button className="text-button" type="button" disabled={deal.rent_roll.length >= 500} onClick={() => setDeal((current) => ({ ...current, rent_roll: [...current.rent_roll, newTenant(current)] }))}>+ Add tenant</button>}
        <details className="form-section"><summary><b>06</b> Exit assumptions <small>Disposition | sensitivity</small></summary><div className="section-body fields three-cols"><Field label="Exit capitalization rate" value={deal.exit_cap_rate * 100} type="number" suffix="%" onChange={(value) => update('exit_cap_rate', Number(value) / 100)} /><Field label="Cost of sale" value={deal.sale_cost_rate * 100} type="number" suffix="%" onChange={(value) => update('sale_cost_rate', Number(value) / 100)} /><Field label="Hold period" value={deal.hold_years} select options={holds.map(String)} suffix="years" onChange={(value) => update('hold_years', Number(value))} /></div></details>
        <div className="row-add-wrap">{deal.property_type === 'multifamily' ? <button className="text-button row-add" type="button" onClick={() => setDeal((current) => { const source = current.unit_mix[0]; return source ? { ...current, units: current.units + 1, unit_mix: [...current.unit_mix, { ...source, unit_type: 'Additional type', count: 1 }] } : current })}>+ Add unit type</button> : <button className="text-button row-add" type="button" disabled={deal.rent_roll.length >= 500} onClick={() => setDeal((current) => ({ ...current, rent_roll: [...current.rent_roll, newTenant(current)] }))}>+ Add tenant</button>}</div>
        <details className="form-section"><summary><b>07</b> Investor waterfall <small>LP economics | configurable promote tiers</small></summary><div className="section-body"><div className="fields three-cols"><Field label="GP co-invest" value={deal.investor.gp_coinvest_pct * 100} type="number" suffix="%" onChange={(value) => updateInvestor('gp_coinvest_pct', Number(value) / 100)} /><Field label="Preferred return" value={deal.investor.preferred_return_rate * 100} type="number" suffix="%" onChange={(value) => updateInvestor('preferred_return_rate', Number(value) / 100)} /><Field label="Minimum investment" value={deal.investor.minimum_investment} type="number" prefix="$" onChange={(value) => updateInvestor('minimum_investment', Number(value))} /></div><label className="catch-up-toggle"><input type="checkbox" checked={deal.investor.gp_catch_up} onChange={(event) => updateInvestor('gp_catch_up', event.target.checked)} /><span>Enable GP catch-up</span></label><div className="tier-heading"><h3>Distribution tiers</h3><span>{deal.investor.tiers.length} configured</span></div>{deal.investor.tiers.map((tier, index) => <div className="tier-row" key={`${tier.name}-${index}`}><Field label="Tier name" value={tier.name} onChange={(value) => updateTier(index, 'name', value)} /><Field label="LP IRR hurdle" value={tier.hurdle_irr === null ? '' : tier.hurdle_irr * 100} type="number" suffix="%" onChange={(value) => updateTier(index, 'hurdle_irr', value === '' ? null : Number(value) / 100)} /><Field label="LP split" value={tier.lp_split * 100} type="number" suffix="%" onChange={(value) => updateTier(index, 'lp_split', Number(value) / 100)} /><Field label="GP split" value={tier.gp_split * 100} type="number" suffix="%" onChange={(value) => updateTier(index, 'gp_split', Number(value) / 100)} /><button className="tier-remove" type="button" aria-label={`Remove ${tier.name}`} disabled={deal.investor.tiers.length <= 1} onClick={() => setDeal((current) => ({ ...current, investor: { ...current.investor, tiers: current.investor.tiers.filter((_, tierIndex) => tierIndex !== index) } }))}>x</button></div>)}<button className="text-button" type="button" onClick={() => updateInvestor('tiers', [...deal.investor.tiers, { name: `Tier ${deal.investor.tiers.length + 1}`, hurdle_irr: null, lp_split: 1, gp_split: 0 }])}>+ Add tier</button>{results?.waterfall && <div className="investor-metrics"><Metric label="LP net IRR" value={percent(results.waterfall.lp_irr)} /><Metric label="LP equity multiple" value={`${results.waterfall.lp_equity_multiple.toFixed(2)}x`} /><Metric label="GP net IRR" value={percent(results.waterfall.gp_irr)} /><Metric label="GP equity multiple" value={`${results.waterfall.gp_equity_multiple.toFixed(2)}x`} /></div>}</div></details>
        <details className="form-section" open><summary><b>08</b> Report images <small>Optional | saved with this deal</small></summary><div className="image-upload-grid">{imageSlots.map(({ slot, label }) => { const image = images.find((item) => item.slot === slot); return <div className="image-upload-card" key={slot}><div><strong>{label}</strong><small>{image?.original_name ?? 'Illustrative fallback in PDF'}</small></div>{image && <button className="image-remove" type="button" onClick={() => void deleteImage(image)} disabled={busy}>Remove</button>}<label className="image-picker"><span>{image ? 'Replace image' : 'Choose image'}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadImage(slot, file); event.currentTarget.value = '' }} disabled={busy} /></label></div> })}</div><p className="image-upload-note">JPEG, PNG, or WebP up to 10 MB. Uploaded images replace the matching illustrative image in the PDF.</p></details>
        {deal.property_type !== 'multifamily' && <RentRollWorkspace deal={deal} busy={busy} onApply={(rows) => { setDeal((current) => ({ ...current, rent_roll: rows })); setResults(null); setNotice('Rent roll applied to this draft; recalculate and save to keep changes') }} onNotice={setNotice} />}
        <div className="form-footer"><span>Assumptions are stored locally in this installation.</span><button className="primary-button" type="submit" disabled={busy}>Recalculate underwriting</button></div>
      </form>

      <aside className="results-panel"><p className="eyebrow">Live underwriting</p><h2>Returns snapshot</h2>{results ? <><div className="hero-metric"><span>Levered IRR</span><strong>{percent(results.levered_irr)}</strong><small>{deal.hold_years}-year hold | monthly cash flow</small></div><div className="metric-grid"><Metric label="Unlevered IRR" value={percent(results.unlevered_irr)} /><Metric label="Equity multiple" value={`${results.levered_equity_multiple.toFixed(2)}x`} /><Metric label="Average cash-on-cash" value={percent(results.average_cash_on_cash)} /><Metric label="Stabilized yield on cost" value={percent(results.stabilized_yield_on_cost)} /></div><div className="capital-lines"><p>Total project cost <strong>{money(results.total_uses)}</strong></p><p>Senior &amp; other debt <strong>{money(results.total_debt)}</strong></p><p>Calculated equity need <strong>{money(results.required_equity)}</strong></p><p>Gross exit value <strong>{money(results.exit_value)}</strong></p></div><h3 className="table-title">Annual cash flow <small>Project level</small></h3><div className="cash-table"><div><span>Year</span><span>NOI</span><span>Levered CF</span></div>{results.annual_cash_flows.map((row) => <div key={row.year}><span>{String(row.year).padStart(2, '0')}</span><span>{money(row.net_operating_income)}</span><strong>{money(row.levered_cash_flow)}</strong></div>)}</div><h3 className="table-title">Exit cap sensitivity <small>Levered IRR</small></h3><div className="sensitivity-bars">{results.exit_cap_sensitivity.map((point) => <div key={point.exit_cap_rate}><strong>{percent(point.levered_irr)}</strong><i style={{ height: `${Math.max(4, (point.levered_irr ?? 0) * 75)}px` }} /><span>{percent(point.exit_cap_rate)}</span></div>)}</div><h3 className="table-title">Hold period <small>Levered IRR</small></h3><div className="hold-sensitivity">{results.hold_period_sensitivity.map((point) => <div key={point.hold_years}><span>{point.hold_years} yr</span><strong>{percent(point.levered_irr)}</strong></div>)}</div><p className="caveat">Project-level outputs only. Investor waterfall allocations are not included in this implementation slice.</p></> : <p className="empty-results">Run the model to see project returns and annual cash flows.</p>}</aside>
      </div>
    </main>
  </div>
}

function RentRollWorkspace({ deal, busy, onApply, onNotice }: { deal: Deal; busy: boolean; onApply: (rows: TenantRow[]) => void; onNotice: (message: string) => void }) {
  const [preview, setPreview] = useState<RentRollPreview | null>(null)
  const [filename, setFilename] = useState('')
  const [loading, setLoading] = useState(false)

  async function upload(file: File) {
    setLoading(true)
    setPreview(null)
    const form = new FormData()
    form.append('file', file)
    form.append('analysis_date', deal.analysis_start_date)
    try {
      const response = await fetch('/api/rent-roll/preview', { method: 'POST', body: form })
      if (!response.ok) throw new Error(await errorMessage(response))
      setPreview((await response.json()) as RentRollPreview)
      setFilename(file.name)
      onNotice('Review the imported rent roll before applying it')
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Could not read rent roll') }
    finally { setLoading(false) }
  }

  function edit(index: number, change: Partial<TenantRow>) {
    setPreview((current) => current && ({ ...current, rows: current.rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...change } : row) }))
  }

  const rows = preview?.rows ?? []
  const totalArea = rows.reduce((sum, row) => sum + row.area_sf, 0)
  const occupiedArea = rows.reduce((sum, row) => sum + (row.vacant ? 0 : row.area_sf), 0)
  const missingMarket = rows.some((row) => row.market_rent_per_sf <= 0)
  const areaMismatch = deal.total_nra_sf > 0 && Math.abs(totalArea - deal.total_nra_sf) > 0.01
  const invalidRows = rows.some((row) => !row.name.trim() || row.area_sf <= 0 || !row.lease_start || !row.lease_end || row.lease_end < row.lease_start || (row.extension_end && (row.extension_end < row.lease_end || !row.rent_steps.some((step) => step.effective_date <= row.lease_end))))

  return <section className="rent-workspace" aria-label="Rent roll import">
    <div className="rent-workspace-head"><h3>Rent roll import</h3><label className="image-picker">Choose file<input type="file" accept=".csv,.xlsx,.pdf" disabled={busy || loading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.currentTarget.value = '' }} /></label><button className="text-button" type="button" disabled={busy || loading} onClick={() => { setPreview({ rows: structuredClone(deal.rent_roll), warnings: [], total_area_sf: 0, occupied_area_sf: 0, annual_base_rent: 0 }); setFilename('Current deal') }}>Edit existing details</button></div>
    {loading && <p role="status">Reading rent roll...</p>}
    {preview && <>
      <p className="rent-summary"><strong>{filename}</strong> · {rows.length} suites · {totalArea.toLocaleString()} SF · {occupiedArea.toLocaleString()} occupied SF {deal.total_nra_sf > 0 && `· Property: ${deal.total_nra_sf.toLocaleString()} SF`}</p>
      {deal.total_nra_sf > totalArea && <p className="rent-warning">{(deal.total_nra_sf - totalArea).toLocaleString()} SF is not assigned to a suite. Add a vacant row or reconcile property area before forecasting.</p>}
      {deal.total_nra_sf > 0 && totalArea > deal.total_nra_sf && <p className="rent-warning">Rent roll area exceeds property rentable area. Reconcile area before applying.</p>}
      {preview.warnings.length > 0 && <ul className="rent-warnings">{preview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      <div className="rent-rows">{rows.map((row, index) => <details key={`${row.suite || row.name}-${index}`} className="rent-row"><summary>{row.suite || 'No suite'} · {row.name} <span>{row.area_sf.toLocaleString()} SF · {row.vacant ? 'Vacant' : money(row.current_rent)}{!row.vacant && (row.rent_basis === 'per_sf_year' ? '/SF/yr' : '/month')}</span></summary><div className="fields three-cols">
        <Field label="Suite" value={row.suite ?? ''} onChange={(value) => edit(index, { suite: value })} /><Field label="Tenant" value={row.name} onChange={(value) => edit(index, { name: value })} /><Field label="Area" type="number" suffix="SF" value={row.area_sf} onChange={(value) => edit(index, { area_sf: Number(value) })} />
        <label className="catch-up-toggle"><input type="checkbox" checked={row.vacant ?? false} onChange={(event) => edit(index, { vacant: event.target.checked, current_rent: event.target.checked ? 0 : row.current_rent })} />Vacant</label>
        <Field label="Lease start" type="date" value={row.lease_start} onChange={(value) => edit(index, { lease_start: value })} /><Field label="Lease end" type="date" value={row.lease_end} onChange={(value) => edit(index, { lease_end: value })} />
        <Field label="Current base rent" type="number" prefix="$" value={row.current_rent} onChange={(value) => edit(index, { current_rent: Number(value) })} /><Field label="Rent basis" select options={['per_sf_year', 'per_month']} value={row.rent_basis} onChange={(value) => edit(index, { rent_basis: value as TenantRow['rent_basis'] })} /><Field label="Lease structure" select options={['gross', 'modified_gross', 'nn', 'nnn']} value={row.lease_structure} onChange={(value) => edit(index, { lease_structure: value as TenantRow['lease_structure'] })} />
        {row.lease_structure === 'nn' && <div className="rent-recoveries">Recoverable expenses{(['property_taxes', 'insurance', 'cam'] as const).map((category) => <label key={category}><input type="checkbox" checked={row.recoverable_expenses.includes(category)} onChange={(event) => edit(index, { recoverable_expenses: event.target.checked ? [...row.recoverable_expenses, category] : row.recoverable_expenses.filter((expense) => expense !== category) })} />{category.replaceAll('_', ' ')}</label>)}</div>}
        {row.lease_structure === 'modified_gross' && <Field label="Expense stop / SF" type="number" prefix="$" value={row.expense_stop_per_sf} onChange={(value) => edit(index, { expense_stop_per_sf: Number(value) })} />}
        <Field label="Market rent / SF / yr" type="number" prefix="$" value={row.market_rent_per_sf} onChange={(value) => edit(index, { market_rent_per_sf: Number(value) })} /><Field label="Vacant suite lease-up" type="date" value={row.lease_up_date ?? ''} onChange={(value) => edit(index, { lease_up_date: value || null })} /><Field label="Agreed extension end" type="date" value={row.extension_end ?? ''} onChange={(value) => edit(index, { extension_end: value || null })} />
        <Field label="Renewal rent / SF / yr" type="number" prefix="$" value={row.renewal_rent_per_sf ?? ''} onChange={(value) => edit(index, { renewal_rent_per_sf: value === '' ? null : Number(value) })} /><Field label="Renewal probability" type="number" suffix="%" value={row.renewal_probability * 100} onChange={(value) => edit(index, { renewal_probability: Number(value) / 100 })} /><Field label="Downtime" type="number" suffix="months" value={row.downtime_months} onChange={(value) => edit(index, { downtime_months: Number(value) })} /><Field label="New lease term" type="number" suffix="months" value={row.new_lease_term_months} onChange={(value) => edit(index, { new_lease_term_months: Number(value) })} />
        <Field label="Renewal TI / SF" type="number" prefix="$" value={row.renewal_ti_per_sf ?? 0} onChange={(value) => edit(index, { renewal_ti_per_sf: Number(value) })} /><Field label="New lease TI / SF" type="number" prefix="$" value={row.new_lease_ti_per_sf ?? 0} onChange={(value) => edit(index, { new_lease_ti_per_sf: Number(value) })} /><Field label="Renewal commission" type="number" suffix="%" value={(row.renewal_commission_rate ?? 0) * 100} onChange={(value) => edit(index, { renewal_commission_rate: Number(value) / 100 })} /><Field label="New lease commission" type="number" suffix="%" value={(row.new_lease_commission_rate ?? 0) * 100} onChange={(value) => edit(index, { new_lease_commission_rate: Number(value) / 100 })} />
        {row.rent_steps.map((step, stepIndex) => <div className="rent-step" key={stepIndex}><Field label="Rent step date" type="date" value={step.effective_date} onChange={(value) => edit(index, { rent_steps: row.rent_steps.map((item, itemIndex) => stepIndex === itemIndex ? { ...item, effective_date: value } : item) })} /><Field label="Step rent (same basis)" type="number" prefix="$" value={step.rent} onChange={(value) => edit(index, { rent_steps: row.rent_steps.map((item, itemIndex) => stepIndex === itemIndex ? { ...item, rent: Number(value) } : item) })} /><button type="button" onClick={() => edit(index, { rent_steps: row.rent_steps.filter((_, itemIndex) => itemIndex !== stepIndex) })}>Remove step</button></div>)}
        <button type="button" className="text-button" onClick={() => edit(index, { rent_steps: [...row.rent_steps, { effective_date: row.lease_start, rent: row.current_rent }] })}>Add rent step</button><button type="button" className="text-button" onClick={() => setPreview((current) => current && ({ ...current, rows: current.rows.filter((_, rowIndex) => rowIndex !== index) }))}>Remove suite</button>
      </div></details>)}</div>
      <div className="rent-actions"><button type="button" className="text-button" disabled={rows.length >= 500} onClick={() => setPreview((current) => current && ({ ...current, rows: [...current.rows, { ...newTenant(deal), suite: '', vacant: true, market_rent_per_sf: 0 }] }))}>Add vacant suite</button><button type="button" onClick={() => setPreview(null)}>Cancel</button><button type="button" className="primary-button" disabled={busy || rows.length === 0 || missingMarket || areaMismatch || invalidRows} onClick={() => { if (window.confirm(`Replace ${deal.rent_roll.length} current rows with ${rows.length} reviewed rows?`)) { onApply(rows); setPreview(null) } }}>Apply to draft</button></div>
      {missingMarket && <p className="rent-warning">Enter market rent for every suite to underwrite vacant space and lease rollover.</p>}
      {invalidRows && <p className="rent-warning">Check tenant names, areas, and lease or extension dates.</p>}
    </>}
  </section>
}

function Field({ label, value, onChange, type = 'text', prefix, suffix, select = false, options = [] }: { label: string; value: string | number; onChange: (value: string) => void; type?: string; prefix?: string; suffix?: string; select?: boolean; options?: string[] }) {
  return <label className="field"><span>{label}</span><span className="input-wrap">{prefix && <i>{prefix}</i>}{select ? <select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option} value={option}>{option.replaceAll('_', ' ')}</option>)}</select> : <input type={type} step={type === 'number' ? 'any' : undefined} value={value} onChange={(event) => onChange(event.target.value)} />}{suffix && <i>{suffix}</i>}</span></label>
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }

function changeUnit<K extends keyof UnitMixRow>(setDeal: Dispatch<SetStateAction<Deal>>, index: number, key: K, value: UnitMixRow[K]) {
  setDeal((current) => ({ ...current, unit_mix: current.unit_mix.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row) }))
}

function changeTenant<K extends keyof TenantRow>(setDeal: Dispatch<SetStateAction<Deal>>, index: number, key: K, value: TenantRow[K]) {
  setDeal((current) => ({ ...current, rent_roll: current.rent_roll.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row) }))
}

function newTenant(deal: Deal): TenantRow {
  const [year, month, day] = deal.analysis_start_date.split('-')
  return { name: 'New tenant', area_sf: Math.max(1, deal.total_nra_sf / Math.max(deal.rent_roll.length + 1, 1)), lease_start: deal.analysis_start_date, lease_end: `${Number(year) + deal.hold_years}-${month}-${day}`, current_rent: 0, rent_basis: 'per_sf_year', lease_structure: 'nnn', recoverable_expenses: ['property_taxes', 'cam'], expense_stop_per_sf: 0, renewal_probability: 0.7, downtime_months: 3, market_rent_per_sf: 0, new_lease_term_months: 60, renewal_rent_per_sf: null, rent_steps: [] }
}

async function errorMessage(response: Response) {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
  return typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`
}

export default App
