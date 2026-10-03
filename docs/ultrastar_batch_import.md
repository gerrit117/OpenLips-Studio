# Local UltraStar batch import

Choose **UltraStar batch import** on the start screen or in **File**.
Select multiple TXT files or a song folder. Folder discovery includes
subfolders and is bounded to 1,000 TXT files per operation.

Studio preserves imported notes, timing and lyrics. It first uses existing
local media named in the TXT. If an asset is not declared, it accepts a
same-name or otherwise unique local audio/video file. Covers use declared
metadata, a unique cover candidate such as `[CO]`, or a single available
image. Ambiguous files are not guessed; background images are not preferred
over a recognized cover. This operation does not download missing media.

Invalid TXT files are reported without discarding successful imports.
Source TXT, media and image files are never modified. Selected projects
retain references to the original local media. Moving those media later requires
updating their paths.

Use **Save projects and open first song** to choose a destination folder
and continue editing. Each batch is saved in a separate `OpenLips-…`
subfolder to avoid overwriting existing projects. Alternatively, use the
Song Pack export button to start the existing automatic DLC workflow
directly, without finding or selecting the saved project files. This direct
export keeps recovery projects in Studio's application-data `batch-imports`
folder; it does not ask for a project destination.
Current Song Packs support up to 16 songs per package. Technical export
validation remains enabled; editor review is not required for every song.

The lightweight Studio installer excludes optional CPU/AMD AI runtimes.
Heavy AI operations download and verify their runtime when needed, with
progress and cancellation. When no complete AMD release is available,
Studio automatically selects the available CPU runtime and displays a
notice. Basic built-in pitch analysis does not require that heavy runtime.
