
// src/app/api/users/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseUserJSONFields } from '@/lib/server/database';
import type { User } from '@/types';
// In a real app, use a library like bcrypt for password hashing
// import bcrypt from 'bcryptjs';

export async function GET() {
  try {
    const db = await getDb();
    const usersRaw = await db.all('SELECT id, username, role, permissions, activeBreakId, auto_enter_after_scan FROM users'); // Exclude password
    const users = usersRaw.map(parseUserJSONFields);
    return NextResponse.json(users);
  } catch (error) {
    console.error('Failed to fetch users:', error);
    return NextResponse.json({ message: 'Failed to fetch users' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  let db;
  let rawUserData: any; 
  let parsedUserDataSuccessful = false;

  try {
    try {
      rawUserData = await request.json();
      parsedUserDataSuccessful = true; 
    } catch (e: unknown) {
      let parseErrorMessage = "Invalid JSON in request body.";
      if (e instanceof SyntaxError) {
        parseErrorMessage = `Invalid JSON in request body: ${e.message}`;
      } else if (e instanceof Error) {
        parseErrorMessage = `Error parsing JSON from request body: ${e.message}`;
      }
      console.error(`Failed to parse request JSON body in POST /api/users. Error: ${String(e)}`, e);
      return NextResponse.json({ message: parseErrorMessage }, { status: 400 });
    }

    if (rawUserData === null || typeof rawUserData !== 'object' || Array.isArray(rawUserData)) {
        return NextResponse.json({ message: 'Request body must be a valid JSON object.' }, { status: 400 });
    }

    const userData = rawUserData as Omit<User, 'id' | 'activeBreakId'>;
    db = await getDb();
    
    if (!userData.username || !userData.password || !userData.role) {
      return NextResponse.json({ message: 'Missing required fields (username, password, role)' }, { status: 400 });
    }
    if (userData.password.trim().length < 6) {
      return NextResponse.json({ message: 'Password must be at least 6 characters' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');

    // const hashedPassword = await bcrypt.hash(userData.password, 10); // Hash password in real app
    const hashedPassword = userData.password; // For demo purposes, direct password

    const newUserId = `user_${Date.now()}_${Math.random().toString(36).substring(2,7)}`;
    const newUserForDb: User = {
        username: userData.username,
        role: userData.role,
        password: hashedPassword,
        id: newUserId,
        permissions: userData.role === 'manager' ? (userData.permissions || []) : [],
        activeBreakId: null,
        autoEnterAfterScan: userData.autoEnterAfterScan ?? true, // Default to true
    };

    await db.run(
      'INSERT INTO users (id, username, password, role, permissions, activeBreakId, auto_enter_after_scan) VALUES (?, ?, ?, ?, ?, ?, ?)',
      newUserForDb.id,
      newUserForDb.username,
      newUserForDb.password,
      newUserForDb.role,
      JSON.stringify(newUserForDb.permissions),
      newUserForDb.activeBreakId,
      newUserForDb.autoEnterAfterScan ? 1 : 0
    );

    await db.run('COMMIT');

    const { password, ...userToReturn } = newUserForDb;
    // Do NOT call parseUserJSONFields here, userToReturn is already correctly typed
    return NextResponse.json(userToReturn, { status: 201 });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in main catch:", e));
    
    let clientErrorMessage = 'An unexpected error occurred while adding the user. Please check server logs for more details.';
    let statusCode = 500;

    if (error && typeof error.message === 'string') {
      if (error.message.includes('UNIQUE constraint failed: users.username')) {
        const problematicUsername = (parsedUserDataSuccessful && rawUserData && typeof rawUserData.username === 'string') ? rawUserData.username : 'provided username';
        clientErrorMessage = `Username "${problematicUsername}" already exists.`;
        statusCode = 409;
      } else if (error instanceof SyntaxError) { 
        clientErrorMessage = `Server encountered a syntax error during processing: ${error.message}. This is an unexpected issue.`;
        console.error('CRITICAL_SYNTAX_ERROR (e.g. "Unexpected end of JSON input") caught in OUTER catch block of POST /api/users.', error);
      } else {
        clientErrorMessage = `Failed to add user due to a server-side issue: ${error.message}`;
        console.error('INTERNAL_SERVER_ERROR in POST /api/users:', error);
      }
    } else {
        console.error('UNKNOWN_INTERNAL_SERVER_ERROR in POST /api/users:', error);
    }
    return NextResponse.json({ message: clientErrorMessage }, { status: statusCode });
  }
}
