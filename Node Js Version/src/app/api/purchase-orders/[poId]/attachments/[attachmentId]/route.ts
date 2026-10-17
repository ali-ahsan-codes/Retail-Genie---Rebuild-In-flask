// This file is kept for organizational purposes, but the DELETE logic is now handled in the parent route
// src/app/api/purchase-orders/[poId]/attachments/route.ts
// for simplicity using a query parameter.
// This file could be used if you wanted a more RESTful path for deletion without query params.
import { NextResponse } from 'next/server';

export async function GET() {
    return NextResponse.json({error: "Method not allowed. Use DELETE with query param on parent route."}, {status: 405});
}
