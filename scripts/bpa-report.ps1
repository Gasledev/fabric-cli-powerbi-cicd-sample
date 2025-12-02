param ($path = $null, $src = ".\..\src\*.Report")

$currentFolder = (Split-Path $MyInvocation.MyCommand.Definition -Parent)

if ($path -eq $null) {
    $path =  $currentFolder
}

Set-Location $path

if ($src) {

    #
    # Download PBI Inspector CLI (if needed)
    #

    $destinationPath = "$currentFolder\_tools\PBIInspector"

    if (!(Test-Path "$destinationPath\win-x64\CLI\PBIRInspectorCLI.exe"))
    {
        New-Item -ItemType Directory -Path $destinationPath -ErrorAction SilentlyContinue | Out-Null            

        Write-Host "Downloading binaries"
    
        $downloadUrl = "https://github.com/NatVanG/PBI-InspectorV2/releases/latest/download/win-x64-CLI.zip"
    
        $zipFile = "$destinationPath\PBIInspector.zip"
    
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile
    
        Expand-Archive -Path $zipFile -DestinationPath $destinationPath -Force     
    
        Remove-Item $zipFile          
    }    
    
    #
    # Load BPA rules
    #

    $rulesPath = "$currentFolder\bpa-report-rules.json"

    if (!(Test-Path $rulesPath))
    {
        Write-Host "Downloading default BPA rules"
    
        Invoke-WebRequest `
            -Uri "https://raw.githubusercontent.com/NatVanG/PBI-InspectorV2/refs/heads/main/Rules/Base-rules.json" `
            -OutFile "$destinationPath\bpa-report-rules.json"
        
        $rulesPath = "$destinationPath\bpa-report-rules.json"
    }

    #
    # Run BPA rules on each PBIR report
    #

    # 🔥 FIX 1 — Find real PBIR reports (definition.pbir)
    $itemsFolders = Get-ChildItem -Path $src -Recurse -Filter "definition.pbir"

    foreach ($itemFolder in $itemsFolders) {

        # 🔥 FIX 2 — Use the folder containing definition.pbir directly
        $itemPath = $itemFolder.Directory.FullName

        Write-Host "Running BPA rules for: '$itemPath'"

        $process = Start-Process `
            -FilePath "$destinationPath\win-x64\CLI\PBIRInspectorCLI.exe" `
            -ArgumentList "-pbipreport ""$itemPath"" -rules ""$rulesPath"" -formats ""GitHub""" `
            -NoNewWindow -Wait -PassThru    

        if ($process.ExitCode -ne 0) {
            throw "Error running BPA rules for: '$itemPath'"
        }    
    }
}
