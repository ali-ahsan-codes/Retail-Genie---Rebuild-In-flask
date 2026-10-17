
import { NextResponse } from "next/server";
import { promises as fsPromises, existsSync, mkdirSync, readdirSync, unlinkSync } from "fs";
import { join } from "path";
import { csvToArray } from "@/lib/csvUtils";

// New upload directory for CSVs
const UPLOAD_DIR_CSV = join(process.cwd(), "uploads", "csv");

async function ensureCsvUploadDirExists() {
  if (!existsSync(UPLOAD_DIR_CSV)) {
    try {
      await fsPromises.mkdir(UPLOAD_DIR_CSV, { recursive: true });
      console.log(`[API STORES CSV] Created upload directory: ${UPLOAD_DIR_CSV}`);
    } catch (error) {
      console.error(`[API STORES CSV] Critical error creating upload directory ${UPLOAD_DIR_CSV}:`, error);
      throw new Error(`Failed to create required CSV upload directory: ${(error as Error).message}`);
    }
  }
}


export async function POST(req: Request) {
  try {
    await ensureCsvUploadDirExists(); 

    const formData = await req.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ message: "No file uploaded" }, { status: 400 });
    }

    if (!(file instanceof File)) {
        return NextResponse.json({ message: "Uploaded item is not a file" }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const originalFilename = file.name || `upload-${Date.now()}.csv`;
    const safeFilename = originalFilename.replace(/[^a-zA-Z0-9._-]/g, '_');
    const filePath = join(UPLOAD_DIR_CSV, safeFilename); // Use new directory

    await fsPromises.writeFile(filePath, buffer);

    try {
      const fileContentForValidation = buffer.toString('utf-8');
      csvToArray(fileContentForValidation); 
      console.log(`[API STORES CSV] CSV file ${safeFilename} uploaded to ${filePath} and basic parsing check passed.`);
    } catch (parseError) {
      console.warn(`[API STORES CSV] Uploaded file ${safeFilename} might not be a valid CSV or parsing failed:`, parseError);
    }

    return NextResponse.json({ message: "File uploaded successfully", filename: safeFilename });

  } catch (error) {
    console.error("[API STORES CSV] Error processing file upload:", error);
    let errorMessage = "File upload failed due to a server error.";
    if (error instanceof Error) {
        errorMessage = error.message;
    }
    return NextResponse.json({ message: errorMessage }, { status: 500 });
  }
}

export async function GET() {
  try {
    await ensureCsvUploadDirExists(); 

    const filesInDir = await fsPromises.readdir(UPLOAD_DIR_CSV); // Read from new directory
    const csvFiles = filesInDir.filter((file) => file.endsWith(".csv"));

    const filesWithData = [];

    for (const file of csvFiles) {
      const filePath = join(UPLOAD_DIR_CSV, file); // Use new directory
      try {
        const fileContent = await fsPromises.readFile(filePath, "utf-8");
        const parsedData = csvToArray(fileContent);
        filesWithData.push({ filename: file, data: parsedData });
      } catch (readOrParseError) {
        console.error(`[API STORES CSV] Error reading or parsing file ${file} from ${filePath}:`, readOrParseError);
        filesWithData.push({ filename: file, data: [], error: `Could not parse file: ${(readOrParseError as Error).message}` });
      }
    }
    return NextResponse.json(filesWithData);
  } catch (error) {
    console.error("[API STORES CSV] Error listing or reading upload directory:", error);
    return NextResponse.json({ message: "Error retrieving CSV data from server" }, { status: 500 });
  }
}

export async function DELETE(req: Request) {
  try {
    await ensureCsvUploadDirExists(); 

    const { searchParams } = new URL(req.url);
    const filename = searchParams.get('filename');
    const action = searchParams.get('action');

    if (action === 'deleteAll') {
      const files = readdirSync(UPLOAD_DIR_CSV); // Use new directory
      let deleteCount = 0;
      for (const file of files) {
        if (file.endsWith(".csv")) {
          try {
            unlinkSync(join(UPLOAD_DIR_CSV, file)); // Use new directory
            deleteCount++;
          } catch (unlinkError) {
            console.error(`[API STORES CSV] Failed to delete file ${file} during deleteAll:`, unlinkError);
          }
        }
      }
      console.log(`[API STORES CSV] Deleted ${deleteCount} CSV files.`);
      return NextResponse.json({ message: `Successfully deleted ${deleteCount} CSV files.` });
    } else if (filename) {
      const sanitizedFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '_');
      const filePath = join(UPLOAD_DIR_CSV, sanitizedFilename); // Use new directory

      try {
        await fsPromises.access(filePath); 
      } catch (accessError) {
        console.warn(`[API STORES CSV] Attempt to delete non-existent file: ${filePath}`);
        return NextResponse.json({ message: "File not found" }, { status: 404 });
      }

      await fsPromises.unlink(filePath);
      console.log(`[API STORES CSV] Deleted file: ${filePath}`);
      return NextResponse.json({ message: `File "${sanitizedFilename}" deleted successfully` });
    } else {
      return NextResponse.json({ message: "Filename query parameter or 'action=deleteAll' is required" }, { status: 400 });
    }

  } catch (error) {
    console.error("[API STORES CSV] Error during DELETE operation:", error);
    let errorMessage = "File operation failed due to a server error.";
    if (error instanceof Error) {
        errorMessage = error.message;
    }
    return NextResponse.json({ message: errorMessage }, { status: 500 });
  }
}
