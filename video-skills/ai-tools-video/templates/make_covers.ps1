# 用法: powershell -ExecutionPolicy Bypass -File make_covers.ps1 -Vol 031 -White "让你" -Yellow "成为大师" -Shot "D:\...\covers\ep31_shot.png" -OutDir "D:\...\ep31"
# 复制 封面.pptx 最后一页 → 改 Vol / 底部文字 / 截图 → 文本居中 → 导出 图片1(3:4) 图片2(4:3)
param([string]$Vol, [string]$White, [string]$Yellow, [string]$Shot, [string]$OutDir,
      [string]$Pptx = "D:\Desktop\temp\视频流\AI工具\封面.pptx")
$ErrorActionPreference = "Stop"
Copy-Item $Pptx ($Pptx -replace '\.pptx$', ".backup-$(Get-Date -Format yyyyMMddHHmm).pptx")
$pp = New-Object -ComObject PowerPoint.Application
$pres = $pp.Presentations.Open($Pptx, 0, 0, 0)
# 出错也要关掉 PowerPoint，不然复制出来的页留在内存里，下次 Open 拿到的是这份脏文档(第35期多出一页 035)
trap { try { $pres.Close() } catch {}; $pp.Quit(); break }
$tpl = $pres.Slides.Item($pres.Slides.Count)
# 最后一页已经是这一期(重做封面)：直接改它，不再复制出第二页同期数
$same = $false
# Vol 标签在组合形状里，要连 GroupItems 一起看
foreach ($sh in @($tpl.Shapes)) {
  $items = @($sh); if ($sh.Type -eq 6) { $items = @($sh.GroupItems) }
  foreach ($it in $items) { if ($it.HasTextFrame -and $it.TextFrame.HasText -and $it.TextFrame.TextRange.Text -match "Vol\.$Vol") { $same = $true } }
}
if ($same) { $s = $tpl } else { $null = $tpl.Duplicate(); $s = $pres.Slides.Item($pres.Slides.Count) }
$pics = @()
foreach ($sh in @($s.Shapes)) {
  if ($sh.HasTextFrame -and $sh.TextFrame.HasText) {
    $tr = $sh.TextFrame.TextRange
    if ($tr.Text -match 'Vol\.\d+') {
      $sh.TextFrame.WordWrap = 0
      $old = [regex]::Match($tr.Text, 'Vol\.(\d+)').Groups[1].Value
      $null = $tr.Replace($old, $Vol)
    } elseif ($tr.Runs().Count -ge 2 -and $sh.Top -gt 3000000 / 12700) {
      # 底部一句话：第一段白色、其余黄色。保留原有字体颜色，只换文字
      $c1 = $tr.Runs(1).Font.Color.RGB; $c2 = $tr.Runs($tr.Runs().Count).Font.Color.RGB
      $tr.Text = $White + $Yellow
      $tr.Characters(1, $White.Length).Font.Color.RGB = $c1
      $tr.Characters($White.Length + 1, $Yellow.Length).Font.Color.RGB = $c2
    }
  }
  if ($sh.Type -eq 13) { $pics += $sh }
}
foreach ($p in $pics) { $l = $p.Left; $t = $p.Top; $w = $p.Width; $h = $p.Height; $p.Delete(); $null = $s.Shapes.AddPicture($Shot, 0, -1, $l, $t, $w, $h) }

# 每个封面区域(黑色大矩形)内：底部文字框横向居中到矩形中心，段落居中
$rects = @($s.Shapes | Where-Object { $_.Type -eq 1 -and -not $_.TextFrame.HasText -and $_.Width -gt 300 -and $_.Height -gt 300 })
foreach ($r in $rects) {
  foreach ($sh in @($s.Shapes)) {
    $cx = $sh.Left + $sh.Width / 2; $cy = $sh.Top + $sh.Height / 2
    $inside = ($cx -ge $r.Left) -and ($cx -le $r.Left + $r.Width) -and ($cy -ge $r.Top) -and ($cy -le $r.Top + $r.Height)
    if ($inside -and $sh.HasTextFrame -and $sh.TextFrame.HasText -and $sh.TextFrame.TextRange.Text -eq ($White + $Yellow)) {
      $sh.TextFrame.TextRange.ParagraphFormat.Alignment = 2
      $sh.TextFrame.WordWrap = 0; $sh.TextFrame.AutoSize = 1
      $sh.Left = $r.Left + ($r.Width - $sh.Width) / 2
    }
  }
}
$pres.Save()

# 导出：另存临时副本 → 放大页面(内容不缩放，只整体平移，超出页面的竖版封面也能完整落进来) → 整页高清导出 → 按封面矩形裁剪。
# 不要复制粘贴到新演示文稿再导出——新文档主题字体不同，英文/数字会丢掉微软雅黑粗体变细(第31期「Token」「90%」踩过)。
# 也不要用 Shape.Export 导出编组——尺寸参数不是像素，文本框还会把边界撑大。
Add-Type -AssemblyName System.Drawing
$tmpPptx = Join-Path $env:TEMP "cover_export_$Vol.pptx"
$pres.SaveCopyAs($tmpPptx)
$q = $pp.Presentations.Open($tmpPptx, 0, 0, 0)
$qs = $q.Slides.Item($q.Slides.Count)
# 放大页面时 PowerPoint 只平移部分形状(Top 为负的不动纵坐标)，所以先记位置，放大后统一手动平移
$pos = @{}; foreach ($sh in @($qs.Shapes)) { $pos[$sh.Name] = @($sh.Left, $sh.Top) }
$dx = (1400 - $q.PageSetup.SlideWidth) / 2; $dy = (900 - $q.PageSetup.SlideHeight) / 2
$q.PageSetup.SlideWidth = 1400; $q.PageSetup.SlideHeight = 900
foreach ($sh in @($qs.Shapes)) { $sh.Left = $pos[$sh.Name][0] + $dx; $sh.Top = $pos[$sh.Name][1] + $dy }
$qrects = @($qs.Shapes | Where-Object { $_.Type -eq 1 -and -not $_.TextFrame.HasText -and $_.Width -gt 300 -and $_.Height -gt 300 })
$scale = 4
$full = Join-Path $env:TEMP "cover_full_$Vol.png"
$qs.Export($full, "PNG", 1400 * $scale, 900 * $scale)
$img = [System.Drawing.Image]::FromFile($full)
foreach ($r in $qrects) {
  if ($r.Height -gt $r.Width) { $w = 900; $h = 1200; $name = "图片1.png" } else { $w = 1200; $h = 900; $name = "图片2.png" }
  $src = New-Object System.Drawing.Rectangle ([int]($r.Left * $scale)), ([int]($r.Top * $scale)), ([int]($r.Width * $scale)), ([int]($r.Height * $scale))
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($img, (New-Object System.Drawing.Rectangle 0, 0, $w, $h), $src, [System.Drawing.GraphicsUnit]::Pixel)
  $bmp.Save((Join-Path $OutDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
$img.Dispose(); Remove-Item $full
$q.Saved = -1; $q.Close(); Remove-Item $tmpPptx
$pres.Close(); $pp.Quit()
Write-Output "covers exported to $OutDir"
