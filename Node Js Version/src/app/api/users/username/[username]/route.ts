
// src/app/api/users/username/[username]/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseUserJSONFields } from '@/lib/server/database';
import type { User } from '@/types';

interface Params {
  params: { username: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    // IMPORTANT: This endpoint returns the password. It should ONLY be called by server-side logic
    // (like a login handler) and never directly exposed or called from the client for general user fetching.
    // For client-side fetching of user details (e.g., for profiles), use the /api/users/[userId] endpoint which omits password.
    const userRaw = await db.get<User>('SELECT * FROM users WHERE username = ?', params.username);
    
    if (!userRaw) {
      return NextResponse.json({ message: 'User not found' }, { status: 404 });
    }
    // Parse permissions if they exist
    const user = parseUserJSONFields(userRaw); 
    return NextResponse.json(user);
  } catch (error) {
    console.error(`Failed to fetch user by username ${params.username}:`, error);
    return NextResponse.json({ message: 'Failed to fetch user' }, { status: 500 });
  }
}
