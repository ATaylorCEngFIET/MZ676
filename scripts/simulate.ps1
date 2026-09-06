param([string]$Top = 'tb_debug_lab')
$ErrorActionPreference = 'Stop'
if ($Top -notin @('tb_debug_lab','tb_uartlite_service')) { throw 'Use scripts/simulate_ip.tcl for the AMD UARTLite integration test.' }
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build/sim_$Top"
New-Item -ItemType Directory -Force -Path $build | Out-Null
Push-Location $build
try {
  $sources = @('lab_pkg','occupancy_checker','cdc_lab','axi_lab','debug_lab','command_parser','uartlite_service','control_bd') | ForEach-Object { Join-Path $root "rtl/$_.vhd" }
  & xvhdl --2008 @sources (Join-Path $root "sim/stream_fifo_model.vhd") (Join-Path $root "sim/simulation_fifo.vhd") (Join-Path $root "sim/$Top.vhd")
  if ($LASTEXITCODE -ne 0) { throw 'VHDL compilation failed' }
  & xelab $Top -s $Top --debug typical
  if ($LASTEXITCODE -ne 0) { throw 'VHDL elaboration failed' }
  & xsim $Top -runall
  if ($LASTEXITCODE -ne 0) { throw 'Simulation failed' }
  $log = Get-Content -Raw xsim.log
  if ($log -match 'Failure:|Fatal:|Error:' -or $log -notmatch 'ALL .* TESTS PASSED') { throw 'Simulation did not pass' }
} finally { Pop-Location }
