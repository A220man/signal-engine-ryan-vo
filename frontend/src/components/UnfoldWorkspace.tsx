import React, { useState, useRef, useCallback } from 'react'
import { Upload, FileText, Download, AlertCircle, CheckCircle, Info, Loader2, ChevronLeft, RotateCcw } from 'lucide-react'
import { api } from '../api/client'

type Step = 'upload' | 'result'

interface BendRecord {
  index: number
  angle_deg: number
  direction: string
  inside_radius: number
  bend_allowance: number
  k_factor: number
  bend_line_start: number[]
  bend_line_end: number[]
  flange_length_side_a: number
  flange_length_side_b: number
  nearest_cut_distance: number
  axis_point: number[]
  axis_direction: number[]
}

interface UnfoldedResult {
  profile_svg: string
  bend_lines: number[][][]
  bends: BendRecord[]
  thickness: number
  k_factor: number
  kerf: number
  blank_area: number
  volume: number
  material_conservation_ratio: number
  warnings: string[]
}

export function UnfoldWorkspace() {
  const [step, setStep] = useState<Step>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<UnfoldedResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [kFactor, setKFactor] = useState(0.33)
  const [kerf, setKerf] = useState(0.0)
  const [showDetails, setShowDetails] = useState(true)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) {
      const ext = selected.name.split('.').pop()?.toLowerCase()
      if (ext !== 'step' && ext !== 'stp') {
        setError('Please select a STEP file (.step or .stp)')
        return
      }
      setFile(selected)
      setError(null)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.add('drag-active')
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.currentTarget.classList.remove('drag-active')
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.remove('drag-active')
    const dropped = e.dataTransfer.files[0]
    if (dropped) {
      const ext = dropped.name.split('.').pop()?.toLowerCase()
      if (ext !== 'step' && ext !== 'stp') {
        setError('Please drop a STEP file (.step or .stp)')
        return
      }
      setFile(dropped)
      setError(null)
    }
  }, [])

  const handleUnfold = async () => {
    if (!file) return
    setLoading(true)
    setError(null)

    try {
      const response = await api.unfoldStepFile(file, { k_factor: kFactor, kerf })
      if (response.success && response.unfolded) {
        setResult(response.unfolded)
        setStep('result')
      } else {
        setError(response.error_message || `Unfold failed: ${response.error_code}`)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to unfold. Check server connection.')
    } finally {
      setLoading(false)
    }
  }

  const handleNewFile = () => {
    setFile(null)
    setResult(null)
    setStep('upload')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const downloadDxf = () => {
    if (!result) return
    // Generate simple DXF content
    const dxfContent = generateDxf(result)
    const blob = new Blob([dxfContent], { type: 'application/dxf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `unfold_${Date.now()}.dxf`
    a.click()
    URL.revokeObjectURL(url)
  }

  const formatNumber = (n: number, decimals = 2) => n.toFixed(decimals)

  if (step === 'upload') {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="border-b border-gray-200 bg-white px-4 py-4">
          <div className="container flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900">Signal Engine</h1>
            <span className="text-sm text-gray-500">Sheet Metal Unfold</span>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl">
            <div className="bg-white rounded-lg border border-gray-200 p-8">
              <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-50 text-blue-600 mb-4">
                  <FileText className="w-8 h-8" />
                </div>
                <h2 className="text-2xl font-semibold text-gray-900">Upload STEP File</h2>
                <p className="text-gray-500 mt-1">Select a sheet-metal part to generate its flat pattern with bend lines</p>
              </div>

              {error && (
                <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
                  <p>{error}</p>
                </div>
              )}

              <div
                className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                  file ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".step,.stp"
                  onChange={handleFileSelect}
                  className="hidden"
                  id="file-upload"
                  data-testid="file-upload"
                />
                <label
                  htmlFor="file-upload"
                  className="cursor-pointer w-full h-full"
                >
                  <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
                  <p className="text-gray-600 mb-2">
                    {file ? `Selected: ${file.name}` : 'Drag and drop a STEP file, or click to browse'}
                  </p>
                  <p className="text-sm text-gray-400">.step or .stp files only</p>
                </label>
              </div>

              {file && (
                <div className="mt-6 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="k-factor" className="block text-sm font-medium text-gray-700 mb-1">K-Factor</label>
                      <input
                        id="k-factor"
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={kFactor}
                        onChange={e => setKFactor(parseFloat(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <p className="text-xs text-gray-500 mt-1">Typical: 0.33 (mild steel), 0.4 (aluminum)</p>
                    </div>
                    <div>
                      <label htmlFor="kerf" className="block text-sm font-medium text-gray-700 mb-1">Kerf Offset (mm)</label>
                      <input
                        id="kerf"
                        type="number"
                        step="0.01"
                        min="0"
                        value={kerf}
                        onChange={e => setKerf(parseFloat(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <p className="text-xs text-gray-500 mt-1">Laser/waterjet kerf compensation</p>
                    </div>
                  </div>

                  <button
                    onClick={handleUnfold}
                    disabled={loading}
                    className="w-full py-3 px-4 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <RotateCcw className="w-5 h-5" />
                        Generate Flat Pattern
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>

            <div className="mt-6 text-center text-sm text-gray-500">
              <p>Supports constant-thickness sheet-metal parts with filleted bends</p>
              <p className="mt-1">Based on <a href="https://github.com/earthtojake/text-to-cad/issues/614" target="_blank" rel="noopener noreferrer">cadgen.unfold proposal</a></p>
            </div>
          </div>
        </main>

        <footer className="border-t border-gray-200 bg-white px-4 py-4">
          <div className="container text-center text-sm text-gray-500">
            Signal Engine &copy; 2024 Ryan Vo &mdash; AI/ML CAD Automation
          </div>
        </footer>
      </div>
    )
  }

  // Result step
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-gray-200 bg-white px-4 py-4">
        <div className="container flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={handleNewFile}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700"
              aria-label="New file"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <h1 className="text-xl font-semibold text-gray-900">Signal Engine</h1>
          </div>
          <span className="text-sm text-gray-500">Flat Pattern Result</span>
        </div>
      </header>

      <main className="flex-1 p-4">
        <div className="container max-w-6xl">
          {error && (
            <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
              <p>{error}</p>
            </div>
          )}

          {result && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <SummaryCard
                  title="Thickness"
                  value={`${formatNumber(result.thickness)} mm`}
                  icon={<FileText className="w-5 h-5" />}
                />
                <SummaryCard
                  title="Bends"
                  value={result.bends.length.toString()}
                  icon={<RotateCcw className="w-5 h-5" />}
                />
                <SummaryCard
                  title="Blank Area"
                  value={`${formatNumber(result.blank_area)} mm²`}
                  icon={<FileText className="w-5 h-5" />}
                />
                <SummaryCard
                  title="Conservation"
                  value={`${(result.material_conservation_ratio * 100).toFixed(1)}%`}
                  icon={<CheckCircle className="w-5 h-5" />}
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* SVG Viewer */}
                <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                    <h3 className="font-medium text-gray-900">Flat Pattern Preview</h3>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setShowDetails(!showDetails)}
                        className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50"
                      >
                        {showDetails ? 'Hide' : 'Show'} Bend Lines
                      </button>
                    </div>
                  </div>
                  <div className="p-4 bg-gray-50 min-h-[400px] flex items-center justify-center">
                    <div className="w-full max-w-3xl" dangerouslySetInnerHTML={{ __html: result.profile_svg }} />
                  </div>
                </div>

                {/* Bend Details Panel */}
                <div className="bg-white rounded-lg border border-gray-200">
                  <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                    <h3 className="font-medium text-gray-900">Bend Details</h3>
                    <button
                      onClick={downloadDxf}
                      className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
                    >
                      <Download className="w-4 h-4" />
                      Download DXF
                    </button>
                  </div>
                  <div className="p-4 max-h-[400px] overflow-y-auto">
                    {result.bends.length === 0 ? (
                      <p className="text-gray-500 text-center py-8">No bends detected</p>
                    ) : (
                      <div className="space-y-4">
                        {result.bends.map((bend, i) => (
                          <BendCard key={i} bend={bend} index={i + 1} />
                        ))}
                      </div>
                    )}

                    {result.warnings.length > 0 && (
                      <div className="mt-6 p-4 rounded-lg bg-yellow-50 border border-yellow-200">
                        <h4 className="font-medium text-yellow-800 mb-2 flex items-center gap-2">
                          <Info className="w-4 h-4" />
                          Warnings
                        </h4>
                        <ul className="text-sm text-yellow-700 space-y-1">
                          {result.warnings.map((w, i) => (
                            <li key={i} className="flex items-start gap-2">
                              <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 mt-1.5 flex-shrink-0" />
                              {w}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>

      <footer className="border-t border-gray-200 bg-white px-4 py-4">
        <div className="container text-center text-sm text-gray-500">
          Signal Engine &copy; 2024 Ryan Vo &mdash; AI/ML CAD Automation
        </div>
      </footer>
    </div>
  )
}

function SummaryCard({ title, value, icon }: { title: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-blue-50 rounded-lg text-blue-600">{icon}</div>
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-semibold text-gray-900">{value}</p>
        </div>
      </div>
    </div>
  )
}

function BendCard({ bend, index }: { bend: BendRecord; index: number }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-medium text-gray-900">Bend {index}</h4>
        <span className="px-2 py-1 text-xs bg-blue-50 text-blue-700 rounded capitalize">
          {bend.direction}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-gray-500">Angle</p>
          <p className="font-medium">{bend.angle_deg.toFixed(1)}°</p>
        </div>
        <div>
          <p className="text-gray-500">Inside Radius</p>
          <p className="font-medium">{bend.inside_radius.toFixed(2)} mm</p>
        </div>
        <div>
          <p className="text-gray-500">Bend Allowance</p>
          <p className="font-medium">{bend.bend_allowance.toFixed(2)} mm</p>
        </div>
        <div>
          <p className="text-gray-500">K-Factor</p>
          <p className="font-medium">{bend.k_factor.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-gray-500">Flange A</p>
          <p className="font-medium">{bend.flange_length_side_a.toFixed(1)} mm</p>
        </div>
        <div>
          <p className="text-gray-500">Flange B</p>
          <p className="font-medium">{bend.flange_length_side_b.toFixed(1)} mm</p>
        </div>
        <div>
          <p className="text-gray-500">Nearest Cut</p>
          <p className="font-medium">{bend.nearest_cut_distance.toFixed(1)} mm</p>
        </div>
        <div className="col-span-2">
          <p className="text-gray-500">Bend Line</p>
          <p className="font-medium font-mono text-xs">
            ({bend.bend_line_start[0].toFixed(1)}, {bend.bend_line_start[1].toFixed(1)}) →
            ({bend.bend_line_end[0].toFixed(1)}, {bend.bend_line_end[1].toFixed(1)})
          </p>
        </div>
      </div>
    </div>
  )
}

function generateDxf(result: UnfoldedResult): string {
  // Simple DXF generation for the flat pattern
  let dxf = `  0
SECTION
  2
HEADER
  9
$ACADVER
  1
AC1027
  9
$INSUNITS
 70
     4
  0
ENDSEC
  0
SECTION
  2
TABLES
  0
TABLE
  2
LAYER
  70
     3
  0
LAYER
  2
CUT
 70
     0
 62
     7
  0
LAYER
  2
BEND
 70
     0
 62
     1
  0
ENDTAB
ENDSEC
  0
SECTION
  2
ENTITIES
`

  // Parse SVG path for CUT layer (simplified - would need proper SVG parsing)
  // For now, output bend lines on BEND layer
  for (const [start, end] of result.bend_lines) {
    dxf += `  0
LINE
  8
BEND
 10
${start[0].toFixed(4)}
 20
${start[1].toFixed(4)}
 30
0.0
 11
${end[0].toFixed(4)}
 21
${end[1].toFixed(4)}
 31
0.0
`
  }

  dxf += `  0
ENDSEC
  0
EOF
`

  return dxf
}

export default UnfoldWorkspace